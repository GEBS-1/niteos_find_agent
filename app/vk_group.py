from __future__ import annotations

import html as htmllib
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

_PHONE_RE = re.compile(
    r"(?:(?:\+7|8)[\s\-\u00a0]*\(?(?:\d{3})\)?[\s\-\u00a0]*\d{3}[\s\-\u00a0]*\d{2}[\s\-\u00a0]*\d{2})"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TAG_RE = re.compile(r"<[^>]+>")


def is_vk_group_url(url: str) -> bool:
    """Community/group — not personal profile (/id123)."""
    low = (url or "").lower()
    if "vk.com" not in low and "vk.ru" not in low:
        return False
    if any(x in low for x in ("/club", "/public", "/event", "/market", "/community")):
        return True
    try:
        path = urlparse(url).path.strip("/").split("/")[0]
    except Exception:
        return False
    if not path:
        return False
    if path.startswith("id") and path[2:].isdigit():
        return False
    if path in {"feed", "join", "login", "away.php", "share.php", "video", "audio", "photos"}:
        return False
    return True


def _norm_group_url(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    return url.split("?")[0].rstrip("/")


def _strip(text: str) -> str:
    text = htmllib.unescape(_TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _uniq(items: list[str], limit: int = 8) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = (item or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
        if len(out) >= limit:
            break
    return out


def _extract_json_blobs(html: str) -> list[dict[str, Any]]:
    blobs: list[dict[str, Any]] = []
    for m in re.finditer(r'{"[\s\S]{80,8000}?}', html):
        chunk = m.group(0)
        if "description" not in chunk and "group" not in chunk.lower():
            continue
        try:
            data = json.loads(chunk)
            if isinstance(data, dict):
                blobs.append(data)
        except json.JSONDecodeError:
            continue
    return blobs


async def fetch_vk_group(
    client: httpx.AsyncClient,
    url: str,
) -> dict[str, Any]:
    """Parse public VK community page for title, description, contacts."""
    url = _norm_group_url(url)
    out: dict[str, Any] = {
        "url": url,
        "title": "",
        "description": "",
        "phones": [],
        "emails": [],
        "links": [],
        "sites": [],
        "contacts_raw": "",
        "ok": False,
    }
    if not is_vk_group_url(url):
        return out

    html = ""
    variants = [
        url,
        url.replace("://vk.ru", "://vk.com"),
        url.replace("://vk.com", "://vk.ru"),
        url.replace("://vk.com", "://m.vk.com").replace("://vk.ru", "://m.vk.com"),
        url.replace("://m.vk.com", "://vk.com"),
    ]
    seen_try: set[str] = set()
    for try_url in variants:
        if try_url in seen_try:
            continue
        seen_try.add(try_url)
        try:
            resp = await client.get(
                try_url,
                headers={"Accept-Language": "ru-RU,ru;q=0.9"},
                timeout=14.0,
            )
        except Exception:
            continue
        if resp.status_code < 400 and resp.text:
            html = resp.text[:250_000]
            out["url"] = _norm_group_url(str(resp.url) if resp.url else try_url)
            break
    if not html:
        return out

    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if title_m:
        out["title"] = _strip(title_m.group(1)).replace("| VK", "").strip()

    for pat in (
        r'property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
        r'content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ):
        m = re.search(pat, html, re.I)
        if m:
            out["description"] = _strip(m.group(1))[:1500]
            break

    if not out["description"]:
        for blob in _extract_json_blobs(html):
            for key in ("description", "activity", "status"):
                val = blob.get(key)
                if isinstance(val, str) and len(val) > 20:
                    out["description"] = val[:1500]
                    break
            if out["description"]:
                break

    text = _strip(html)
    phones = []
    for raw in _PHONE_RE.findall(html):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 10:
            phones.append(raw.strip())
    out["phones"] = _uniq(phones, 5)
    out["emails"] = _uniq(
        [
            e
            for e in _EMAIL_RE.findall(html)
            if not any(b in e.lower() for b in ("vk.com", "vk.ru", "example.com"))
        ],
        5,
    )

    for block_pat in (
        r'class="[^"]*group_info[^"]*"[^>]*>([\s\S]{0,3000}?)</',
        r'group_info[\s\S]{0,2000}',
        r'Контакты[\s\S]{0,1200}',
    ):
        m = re.search(block_pat, html, re.I)
        if m:
            out["contacts_raw"] = _strip(m.group(0) if m.lastindex else m.group())[:2000]
            break

    for raw in re.findall(r'href=["\'](https?://[^"\']+)["\']', html, re.I):
        low = raw.lower()
        if "vk.com" in low or "vk.ru" in low:
            continue
        if any(
            x in low
            for x in ("t.me", "telegram.me", "wa.me", "whatsapp", "max.ru", "instagram", "youtube")
        ):
            out["links"].append(raw)
            continue
        if any(x in low for x in ("login", "share", "oauth", "facebook", "apple.com")):
            continue
        out["sites"].append(raw.split("?")[0].rstrip("/"))
    out["links"] = _uniq(out["links"], 6)
    for m in re.finditer(
        r"(?:https?://)?(?:www\.)?([a-z0-9\-]+(?:\.[a-z0-9\-]+)+(?:/[^\s\"'<]*)?)",
        f"{out.get('description') or ''} {out.get('contacts_raw') or ''}",
        re.I,
    ):
        cand = m.group(0)
        low = cand.lower()
        if any(x in low for x in ("vk.com", "vk.ru", "t.me", "whatsapp", "instagram")):
            continue
        if not cand.startswith("http"):
            cand = "https://" + cand
        out["sites"].append(cand.split("?")[0].rstrip("/"))
    out["sites"] = _uniq(out["sites"], 5)
    out["ok"] = bool(
        out["title"] or out["description"] or out["phones"] or out["emails"] or out["sites"]
    )
    return out


async def extract_group_contacts_llm(
    llm: Any,
    *,
    company: str,
    inn: str,
    group: dict[str, Any],
) -> list[dict[str, str]]:
    """LLM: who to write to in VK group (from open description/contacts)."""
    if not getattr(llm, "available", False):
        return []
    payload = {
        "company": company,
        "inn": inn,
        "group_title": group.get("title"),
        "group_url": group.get("url"),
        "description": (group.get("description") or "")[:1200],
        "contacts_raw": (group.get("contacts_raw") or "")[:1200],
        "phones": group.get("phones") or [],
        "emails": group.get("emails") or [],
    }
    system = """Из описания и контактов группы ВК компании извлеки, КОМУ писать.
Верни JSON: {"contacts": [{"role": "...", "name": "...", "phone": "", "email": "", "note": "..."}]}
role — закупки/директор/администратор/реклама/неизвестно. Если данных нет — contacts: [].
Только то, что явно есть в тексте. Не выдумывай."""
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=600,
        )
    except Exception as exc:
        log.warning("vk group llm extract failed: %s", exc)
        return []
    items = data.get("contacts") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for item in items[:6]:
        if not isinstance(item, dict):
            continue
        row = {
            "role": str(item.get("role") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "phone": str(item.get("phone") or "").strip(),
            "email": str(item.get("email") or "").strip(),
            "note": str(item.get("note") or "").strip(),
        }
        if any(row.values()):
            out.append(row)
    return out
