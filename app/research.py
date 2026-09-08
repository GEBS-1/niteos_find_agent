from __future__ import annotations

import html as htmllib
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

log = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_IMAGE_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.I,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_IMG_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)


def _strip_html(text: str) -> str:
    text = htmllib.unescape(_TAG_RE.sub(" ", text or ""))
    return _WS_RE.sub(" ", text).strip()


def _abs_url(base: str, raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("http"):
        return raw
    try:
        return urljoin(base, raw)
    except Exception:
        return ""


def _og_image(html: str, page_url: str) -> str:
    for pat in (_OG_IMAGE_RE, _OG_IMAGE_RE2):
        m = pat.search(html or "")
        if m:
            return _abs_url(page_url, m.group(1))
    return ""


def _page_images(html: str, page_url: str, limit: int = 6) -> list[str]:
    host = urlparse(page_url).netloc.lower()
    out: list[str] = []
    seen: set[str] = set()
    for raw in _IMG_RE.findall(html or ""):
        url = _abs_url(page_url, raw)
        if not url.startswith("http"):
            continue
        low = url.lower()
        if any(x in low for x in ("pixel", "spacer", "1x1", "logo.svg", "icon.", "favicon")):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= limit:
            break
    if host and not out:
        og = _og_image(html, page_url)
        if og:
            out.append(og)
    return out


async def fetch_page_excerpt(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_chars: int = 2500,
) -> dict[str, Any]:
    """Download public page and return text excerpt for LLM investigator."""
    url = (url or "").strip()
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    out: dict[str, Any] = {
        "url": url,
        "ok": False,
        "title": "",
        "excerpt": "",
        "og_image": "",
        "images": [],
        "status": 0,
    }
    try:
        resp = await client.get(url, timeout=14.0)
    except Exception as exc:
        out["error"] = str(exc)[:120]
        return out
    out["status"] = resp.status_code
    if resp.status_code >= 400 or not resp.text:
        return out
    html = resp.text[:180_000]
    title_m = _TITLE_RE.search(html)
    title = _strip_html(title_m.group(1)) if title_m else ""
    body = _strip_html(html)
    excerpt = body[:max_chars]
    og = _og_image(html, url)
    images = _page_images(html, url)
    if og and og not in images:
        images = [og] + images
    out.update(
        {
            "ok": True,
            "title": title[:200],
            "excerpt": excerpt,
            "og_image": og,
            "images": images[:5],
        }
    )
    return out


async def build_evidence(
    client: httpx.AsyncClient,
    *,
    urls: list[str],
    max_pages: int = 8,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch up to max_pages unique URLs; return snippets + photo URLs."""
    snippets: list[dict[str, Any]] = []
    photos: list[str] = []
    seen_urls: set[str] = set()
    seen_photos: set[str] = set()

    for url in urls:
        key = (url or "").strip().lower().rstrip("/")
        if not key or key in seen_urls:
            continue
        seen_urls.add(key)
        page = await fetch_page_excerpt(client, url)
        if page.get("ok"):
            snippets.append(
                {
                    "url": page["url"],
                    "title": page.get("title") or "",
                    "excerpt": page.get("excerpt") or "",
                }
            )
            for img in page.get("images") or []:
                if img not in seen_photos:
                    seen_photos.add(img)
                    photos.append(img)
        if len(snippets) >= max_pages:
            break
    return snippets, photos[:8]


def dedupe_urls(urls: list[str], limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        key = (u or "").strip().lower().rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(u.strip())
        if len(out) >= limit:
            break
    return out
