"""School-specific contacts: edu.tatar.ru cards + verified VK groups.

Web search (Bing/Brave) is often poisoned for RU queries from this host.
For Tatarstan schools the reliable path is:
  district type/1 list on edu.tatar.ru → school card (phone/email)
  + VK candidates (LLM / heuristics) verified by page body (№ + школа/гимназия).
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

log = logging.getLogger(__name__)

# Kazan / RT district slugs that expose /type/1 school lists
_RT_DISTRICTS = (
    "sovetcki",
    "kirov",
    "nsav",
    "moskow",
    "privolzhskii",
    "privolzhski",
    "vahitov",
    "vahitovskii",
    "aviastroitelnyi",
    "aviastroitelniy",
)

_PHONE_RE = re.compile(
    r"(?:(?:\+7|8)[\s\-\u00a0]*\(?(?:\d{3})\)?[\s\-\u00a0]*\d{3}[\s\-\u00a0]*\d{2}[\s\-\u00a0]*\d{2})"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_school_index_cache: dict[str, str] | None = None


def school_number(text: str) -> str:
    m = re.search(
        r"(?:№|n|номер)\s*(\d{1,4})\b|\b(\d{1,4})\s*(?:школ|сош|лицей|гимнази|нче)",
        (text or "").lower().replace("ё", "е"),
        flags=re.I,
    )
    if not m:
        return ""
    return m.group(1) or m.group(2) or ""


def is_school_context(*, title: str = "", company: str = "") -> bool:
    blob = f"{title} {company}".lower().replace("ё", "е")
    return any(
        w in blob
        for w in (
            "школ",
            "лицей",
            "гимнази",
            "мбоу",
            "маоу",
            "гбоу",
            "сош",
            "детский сад",
        )
    )


def _uniq(items: list[str], limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        s = (raw or "").strip()
        if not s or s.lower() in seen:
            continue
        seen.add(s.lower())
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _norm_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) != 11 or not digits.startswith("7"):
        return ""
    return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"


def parse_edu_tatar_card(html: str) -> dict[str, Any]:
    """Extract phone/email/vk/site from an edu.tatar.ru school card."""
    text = html or ""
    phones: list[str] = []
    cell = re.search(
        r"Телефон:\s*</t[dh]>\s*<t[dh][^>]*>\s*([^<]+)", text, flags=re.I
    )
    if cell:
        phones = [_norm_phone(p) for p in _PHONE_RE.findall(cell.group(1))]
    if not phones:
        phones = [_norm_phone(p) for p in _PHONE_RE.findall(text)]
    phones = [p for p in phones if p and not p.endswith("525-70-99")]  # support
    # For RT school cards, city landline (843) is the reliable line
    local = [p for p in phones if "(843)" in p]
    if local:
        phones = local + [p for p in phones if p not in local]
    emails = [
        e
        for e in _EMAIL_RE.findall(text)
        if "help.edu" not in e.lower() and "tatar.ru" in e.lower()
    ]
    mail_cell = re.search(
        r"E-?Mail:\s*</t[dh]>\s*<t[dh][^>]*>\s*([^<]+)", text, flags=re.I
    )
    if mail_cell:
        cell_mails = [
            e
            for e in _EMAIL_RE.findall(mail_cell.group(1))
            if "help.edu" not in e.lower()
        ]
        if cell_mails:
            emails = cell_mails
    if not emails:
        emails = [
            e
            for e in _EMAIL_RE.findall(text)
            if not any(b in e.lower() for b in ("help.", "example.", "vk-portal"))
        ]
    vks = re.findall(r"https?://(?:www\.)?vk\.(?:com|ru)/[A-Za-z0-9._/-]+", text)
    vks = [u.split("?")[0].rstrip("/") for u in vks]
    sites: list[str] = []
    bad_site = (
        "edu.tatar.ru",
        "uslugi.tatar.ru",
        "ms-edu.tatar.ru",
        "info.edu.tatar.ru",
        "ya-shkolnik",
        "myschool.edu.ru",
        "vk.com",
        "vk.ru",
        "yandex.",
        "google.",
    )
    for m in re.finditer(r'href="(https?://[^"]+)"', text, flags=re.I):
        u = m.group(1)
        host = (urlparse(u).netloc or "").lower()
        if any(bad in host for bad in bad_site):
            continue
        if host.endswith(".tatar.ru") or host.endswith(".edu.ru") or "school" in host or "гимн" in host:
            sites.append(u.split("?")[0].rstrip("/"))
    title = ""
    tm = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    if tm:
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", tm.group(1))).strip()
    return {
        "title": title,
        "phones": _uniq([p for p in phones if p], 4),
        "emails": _uniq(emails, 4),
        "vk": _uniq(vks, 4),
        "sites": _uniq(sites, 4),
    }


def _label_has_number(label: str, num: str) -> bool:
    lab = (label or "").lower().replace("ё", "е")
    if not num:
        return False
    return bool(
        re.search(
            rf"(?:№\s*{num}\b|\b{num}\s*(?:нче|школ|гимнази|лицей|сош)|\b{num}\b)",
            lab,
            flags=re.I,
        )
    )


async def build_edu_tatar_school_index(
    client: httpx.AsyncClient,
) -> dict[str, str]:
    """Map school number → edu.tatar.ru card URL (Kazan districts)."""
    global _school_index_cache
    if _school_index_cache is not None:
        return _school_index_cache
    index: dict[str, str] = {}
    for dist in _RT_DISTRICTS:
        url = f"https://edu.tatar.ru/{dist}/type/1"
        try:
            resp = await client.get(url, timeout=18.0)
        except Exception as exc:
            log.info("edu.tatar list %s failed: %s", dist, exc)
            continue
        if resp.status_code >= 400 or not resp.text:
            continue
        html = resp.text
        for m in re.finditer(
            r'href="([^"]+)"[^>]*>\s*([^<]{3,160})\s*<', html, flags=re.I
        ):
            href, label = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
            low = label.lower().replace("ё", "е")
            if not any(w in low for w in ("школ", "гимназ", "лицей", "мбоу", "маоу", "гбоу")):
                continue
            num = school_number(label)
            if not num:
                continue
            if href.startswith("/"):
                href = urljoin("https://edu.tatar.ru/", href)
            if not href.startswith("http"):
                continue
            # Prefer first hit; keep if empty
            index.setdefault(num, href.split("?")[0])
    _school_index_cache = index
    log.info("edu.tatar school index size=%s", len(index))
    return index


def vk_html_matches_school(
    html: str,
    *,
    num: str,
    title: str = "",
    known_phones: list[str] | None = None,
) -> bool:
    """Accept VK page even with login-wall title if body proves school identity."""
    low = (html or "").lower().replace("ё", "е")
    if not low or len(low) < 800 or not num:
        return False
    digits_blob = re.sub(r"\D", "", low)
    for raw in known_phones or []:
        d = re.sub(r"\D", "", raw or "")
        if len(d) >= 10 and d[-10:] in digits_blob:
            return True
    near = bool(
        re.search(
            rf"(?:гимназ\w*|школ\w*|лицей\w*|сош|мбоу|маоу|гбоу|"
            rf"gymnasium|school|lyceum).{{0,40}}{re.escape(num)}"
            rf"|{re.escape(num)}.{{0,40}}(?:гимназ\w*|школ\w*|лицей\w*|"
            rf"gymnasium|school|lyceum)",
            low,
            flags=re.I,
        )
    )
    if not near:
        return False
    t = (title or "").lower().replace("ё", "е")
    if "казан" in t:
        # Reject generic schoolN pages without Kazan signal
        if not any(x in low for x in ("казан", "kzn", "kazan", "татарстан")):
            return False
    return True


def _norm_group_url(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    return url.split("?")[0].rstrip("/")


async def fetch_vk_school_candidate(
    client: httpx.AsyncClient,
    url: str,
    *,
    num: str,
    title: str = "",
    known_phones: list[str] | None = None,
) -> dict[str, Any] | None:
    from app.vk_group import fetch_vk_group, is_vk_group_url

    url = _norm_group_url(url)
    if not is_vk_group_url(url):
        return None
    parsed = await fetch_vk_group(client, url)
    html = ""
    try:
        resp = await client.get(url, timeout=14.0)
        if resp.status_code < 400:
            html = resp.text or ""
    except Exception:
        html = ""
    title_try = str(parsed.get("title") or "")
    generic = title_try.lower().strip() in {
        "вконтакте | вконтакте",
        "вконтакте",
        "vk",
    } or (title_try.lower().startswith("вконтакте") and len(title_try) < 24)
    label_ok = False
    if not generic and num and num in title_try.lower():
        label_ok = True
    # Phone overlap with edu.tatar is strongest signal under login walls
    phone_ok = False
    parsed_phones = [_norm_phone(p) for p in (parsed.get("phones") or [])]
    parsed_phones = [p for p in parsed_phones if p]
    known = [p for p in (known_phones or []) if p]
    if known and parsed_phones:
        known_tails = {re.sub(r"\D", "", p)[-10:] for p in known}
        for p in parsed_phones:
            if re.sub(r"\D", "", p)[-10:] in known_tails:
                phone_ok = True
                break
    body_ok = vk_html_matches_school(
        html, num=num, title=title, known_phones=known
    )
    if not (label_ok or body_ok or phone_ok):
        return None
    return {
        "url": parsed.get("url") or url,
        "title": title_try,
        "phones": parsed_phones,
        "emails": list(parsed.get("emails") or [])[:3],
        "sites": list(parsed.get("sites") or [])[:3],
        "via": "phone" if phone_ok else ("title" if label_ok else "body"),
    }


def _school_vk_guesses(*, num: str, title: str, city: str) -> list[str]:
    if not num:
        return []
    city_l = (city or "").lower().replace("ё", "е")
    out = [
        f"https://vk.com/gymnasium{num}_kzn",
        f"https://vk.com/gymnasium{num}",
        f"https://vk.com/school{num}_kzn",
        f"https://vk.com/school{num}kazan",
        f"https://vk.com/school{num}",
        f"https://vk.com/shkola{num}",
        f"https://vk.com/shkola_{num}",
        f"https://vk.com/public{num}",
    ]
    if "казан" in city_l:
        out.extend(
            [
                f"https://vk.com/club_school{num}_kzn",
                f"https://vk.com/kznschool{num}",
            ]
        )
    # keep short list; verification filters junk
    return _uniq(out, 10)


async def llm_school_contact_hints(
    llm: Any,
    *,
    title: str,
    company: str,
    city: str,
    address: str,
    num: str,
) -> dict[str, Any]:
    if llm is None or not getattr(llm, "available", False):
        return {}
    try:
        data = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты помощник по школам РФ. Верни JSON: "
                        '{"edu_tatar":"","vk":["https://vk.com/..."],'
                        '"site":"","notes":""}. '
                        "Для Татарстана укажи реальный URL карточки на edu.tatar.ru "
                        "(вида https://edu.tatar.ru/<район>/page....htm или /sch...). "
                        "Не выдумывай телефоны. VK — только если уверен в slug/club. "
                        "Пустые строки допустимы."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Здание: {title}\nЮрлицо: {company}\nГород: {city}\n"
                        f"Адрес: {address}\nНомер: {num or '—'}"
                    ),
                },
            ],
            max_tokens=450,
        )
    except Exception as exc:
        log.info("llm school hints failed: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


async def llm_pick_from_search(
    llm: Any,
    *,
    title: str,
    company: str,
    city: str,
    num: str,
    hits: list[dict[str, str]],
) -> dict[str, Any]:
    """LLM chooses site/VK from real search hits — no inventing URLs."""
    if llm is None or not getattr(llm, "available", False) or not hits:
        return {}
    compact = [
        {
            "title": (h.get("title") or "")[:120],
            "link": h.get("link") or "",
            "snippet": (h.get("snippet") or "")[:220],
        }
        for h in hits[:18]
    ]
    try:
        data = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "По результатам поиска выбери контакты школы. "
                        "Ответь строго JSON: "
                        '{"site":"","vk":"","edu_tatar":"","phones":[],"emails":[],"why":""}. '
                        "Бери URL только из переданных link. Не выдумывай. "
                        "site = официальный сайт; vk = группа ВК; "
                        "edu_tatar = страница edu.tatar.ru если есть."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Школа: {title}\nЮрлицо: {company}\nГород: {city}\n"
                        f"Номер: {num or '—'}\nРезультаты: {compact}"
                    ),
                },
            ],
            max_tokens=500,
        )
    except Exception as exc:
        log.info("llm pick search failed: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


async def discover_school_via_web(
    client: httpx.AsyncClient,
    llm: Any,
    *,
    title: str,
    company: str,
    city: str,
    num: str,
) -> dict[str, Any]:
    """School+city → RouterAI web plugin (или Serper) → контакты."""
    out: dict[str, Any] = {
        "site": "",
        "vk": "",
        "edu_tatar": "",
        "phones": [],
        "emails": [],
        "notes": [],
        "hits": 0,
    }
    uniq_hits: list[dict[str, str]] = []
    picked: dict[str, Any] = {}

    # 1) RouterAI built-in web search — only if HUNT_LLM_WEB=1 (expensive)
    from app.cost_guard import llm_web_enabled

    if llm is not None and getattr(llm, "available", False) and llm_web_enabled():
        try:
            picked = await llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Найди в интернете контакты именно этой школы. "
                            "Ответь строго JSON: "
                            '{"site":"","vk":"","edu_tatar":"","phones":[],"emails":[],"why":""}. '
                            "site = официальный сайт школы; vk = группа ВКонтакте; "
                            "edu_tatar = страница на edu.tatar.ru если есть. "
                            "Не выдумывай URL — только то, что нашлось в поиске. "
                            "Если не уверен — оставь пустую строку."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Школа: {title}\nЮрлицо: {company}\nГород: {city}\n"
                            f"Номер школы: {num or '—'}\n"
                            f"Запросы: официальный сайт, ВКонтакте, телефон, edu.tatar.ru"
                        ),
                    },
                ],
                max_tokens=600,
                web=True,
                web_max_results=10,
            )
            cites = list(picked.pop("_citations", None) or [])
            uniq_hits.extend(cites)
            out["notes"].append(f"RouterAI web: {len(cites)} источников")
        except Exception as exc:
            out["notes"].append(f"RouterAI web fail: {exc}")

    # 2) Optional Serper fallback (if key ever present)
    if len(uniq_hits) < 3:
        try:
            from app.websearch import serper_api_key, web_search

            if serper_api_key():
                queries = [
                    f"{title} {city} официальный сайт".strip(),
                    f"{title} {city} ВКонтакте".strip(),
                ]
                if num:
                    queries.insert(0, f"школа №{num} {city} официальный сайт")
                extra: list[dict[str, str]] = []
                for q in queries[:3]:
                    extra.extend(await web_search(client, q, num=5))
                uniq_hits.extend(extra)
                out["notes"].append(f"Serper fallback: +{len(extra)}")
        except Exception as exc:
            out["notes"].append(f"serper: {exc}")

    seen: set[str] = set()
    cleaned: list[dict[str, str]] = []
    for h in uniq_hits:
        link = (h.get("link") or "").strip()
        if not link or link in seen:
            continue
        seen.add(link)
        cleaned.append(h)
    uniq_hits = cleaned
    out["hits"] = len(uniq_hits)

    # If web plugin returned JSON but few citations — still use JSON fields,
    # then re-pick only from known hits when we have them.
    if uniq_hits and (
        not picked.get("site") and not picked.get("vk") and not picked.get("edu_tatar")
    ):
        picked = await llm_pick_from_search(
            llm, title=title, company=company, city=city, num=num, hits=uniq_hits
        )

    allowed = {h["link"] for h in uniq_hits}
    # Web plugin often puts the real VK/site in JSON but not in citations.
    soft = not allowed
    junk_site_hosts = (
        "orgpage.",
        "orgs.biz",
        "list-org.",
        "synapsenet.",
        "goodschools.",
        "check.tochka.",
        "akazan.",
        "ouuo.ru",
        "2gis.",
        "yandex.",
        "wikipedia.",
    )

    def _accept(url: str, *, kind: str = "") -> str:
        url = (url or "").strip()
        if not url.startswith("http"):
            return ""
        clean = url.split("?")[0].rstrip("/")
        host = (urlparse(clean).netloc or "").lower()
        if kind == "site" and any(j in host for j in junk_site_hosts):
            return ""
        if soft:
            return clean
        if clean in allowed or url in allowed:
            return clean
        if host and any(host == (urlparse(u).netloc or "").lower() for u in allowed):
            return clean
        # Trust VK / edu.tatar from web-enabled LLM even without citation match
        if kind in ("vk", "edu") and any(
            x in host for x in ("vk.com", "vk.ru", "edu.tatar.ru")
        ):
            return clean
        return ""

    out["site"] = _accept(str(picked.get("site") or ""), kind="site")
    out["vk"] = _accept(str(picked.get("vk") or ""), kind="vk")
    edu_raw = picked.get("edu_tatar")
    if isinstance(edu_raw, str):
        out["edu_tatar"] = _accept(edu_raw, kind="edu")
    elif edu_raw and out["site"] and "edu.tatar.ru" in out["site"]:
        out["edu_tatar"] = out["site"]
    if out["site"] and "edu.tatar.ru" in out["site"]:
        if not out["edu_tatar"]:
            out["edu_tatar"] = out["site"]
        out["site"] = ""  # edu.tatar отдельно, не как «официальный сайт»
    for p in picked.get("phones") or []:
        norm = _norm_phone(str(p))
        if norm:
            out["phones"].append(norm)
    for e in picked.get("emails") or []:
        em = str(e or "").strip()
        if "@" in em:
            out["emails"].append(em)

    if not out["edu_tatar"]:
        for h in uniq_hits:
            if "edu.tatar.ru" in (h.get("link") or ""):
                out["edu_tatar"] = h["link"].split("?")[0]
                break
    if not out["vk"]:
        for h in uniq_hits:
            link = h.get("link") or ""
            if "vk.com/" in link or "vk.ru/" in link:
                out["vk"] = link.split("?")[0]
                break
    if not out["site"]:
        for h in uniq_hits:
            link = h.get("link") or ""
            host = (urlparse(link).netloc or "").lower()
            if any(
                bad in host
                for bad in (
                    "vk.com",
                    "vk.ru",
                    "yandex.",
                    "2gis.",
                    "wikipedia.",
                    "edu.tatar.ru",
                    *junk_site_hosts,
                )
            ):
                continue
            if host:
                out["site"] = link.split("?")[0]
                break
    if not uniq_hits and not out["site"] and not out["vk"] and not out["phones"]:
        out["notes"].append("поиск не вернул ссылок")
    if picked.get("why"):
        out["notes"].append(f"LLM: {str(picked.get('why'))[:120]}")
    return out

async def scrape_maps_org_contacts(
    client: httpx.AsyncClient, maps_url: str
) -> dict[str, Any]:
    """VK links from Yandex Maps org page (phones in Maps HTML are too noisy)."""
    out: dict[str, Any] = {"phones": [], "vk": [], "sites": []}
    if not maps_url or "maps" not in maps_url or "/org/" not in maps_url:
        return out
    try:
        resp = await client.get(maps_url, timeout=16.0)
    except Exception:
        return out
    if resp.status_code >= 400 or not resp.text:
        return out
    html = resp.text
    out["vk"] = _uniq(
        [
            u.split("?")[0].rstrip("/")
            for u in re.findall(
                r"https?://(?:www\.)?vk\.(?:com|ru)/[A-Za-z0-9._/-]+", html
            )
        ],
        4,
    )
    return out


async def enrich_school_contacts(
    client: httpx.AsyncClient,
    *,
    title: str,
    company: str,
    city: str,
    address: str = "",
    maps_url: str = "",
    llm: Any | None = None,
) -> dict[str, Any]:
    """Return verified school contacts (phones/emails/site/vk) + notes."""
    out: dict[str, Any] = {
        "phones": [],
        "emails": [],
        "site": "",
        "vk": "",
        "edu_url": "",
        "notes": [],
    }
    if not is_school_context(title=title, company=company):
        return out
    num = school_number(title) or school_number(company)
    notes: list[str] = []
    title_for_vk = f"{title} {city}".strip()

    # 0) Simple open-web path: search API + LLM pick (needs SERPER_API_KEY)
    web = await discover_school_via_web(
        client, llm, title=title or company, company=company, city=city, num=num
    )
    notes.extend(web.get("notes") or [])
    if web.get("edu_tatar") and not out.get("edu_url"):
        # will fetch below via edu_url path
        pass
    if web.get("phones"):
        out["phones"].extend(web["phones"])
    if web.get("emails"):
        out["emails"].extend(web["emails"])
    if web.get("site"):
        out["site"] = web["site"]
    if web.get("vk"):
        verified = await fetch_vk_school_candidate(
            client,
            web["vk"],
            num=num,
            title=title_for_vk,
            known_phones=out["phones"],
        )
        if verified:
            out["vk"] = verified["url"]
            notes.append(f"ВК из поиска: {out['vk']}")
        else:
            # keep candidate for UI if phone already known from edu later
            out["vk"] = web["vk"]
            notes.append(f"ВК кандидат из поиска (слабая сверка): {web['vk']}")

    # 1) edu.tatar.ru index by school number (Tatarstan)
    edu_url = str(web.get("edu_tatar") or "")
    city_l = (city or "").lower().replace("ё", "е")
    addr_l = (address or "").lower().replace("ё", "е")
    in_rt = any(
        x in f"{city_l} {addr_l} {company.lower()}"
        for x in ("казан", "татарстан", "альметьев", "набережн", "нижнекам", "челны")
    )
    if in_rt and num and not edu_url:
        try:
            index = await build_edu_tatar_school_index(client)
            edu_url = index.get(num) or ""
        except Exception as exc:
            notes.append(f"edu.tatar index: {exc}")

    hints = await llm_school_contact_hints(
        llm,
        title=title,
        company=company,
        city=city,
        address=address,
        num=num,
    )
    hint_edu = str(hints.get("edu_tatar") or "").strip()
    if not edu_url and hint_edu.startswith("http") and "edu.tatar.ru" in hint_edu:
        edu_url = hint_edu.split("?")[0]

    if edu_url:
        try:
            resp = await client.get(edu_url, timeout=18.0)
            html = resp.text or ""
        except Exception as exc:
            html = ""
            notes.append(f"edu.tatar fetch fail: {exc}")
        card = parse_edu_tatar_card(html) if html else {}
        card_ok = False
        if card:
            blob = f"{card.get('title') or ''} {html[:8000]}".lower().replace("ё", "е")
            if num and num in blob and any(
                w in blob for w in ("школ", "гимназ", "лицей", "мбоу", "гбоу")
            ):
                card_ok = True
            if not card.get("phones") and not card.get("emails"):
                card_ok = False
        if card_ok:
            out["edu_url"] = edu_url
            for p in card.get("phones") or []:
                if p not in out["phones"]:
                    out["phones"].append(p)
            out["emails"] = list(card.get("emails") or [])
            if card.get("sites") and not out["site"]:
                host = (urlparse(card["sites"][0]).netloc or "").lower()
                if "uslugi." not in host and "ms-edu." not in host:
                    out["site"] = card["sites"][0]
            notes.append(f"edu.tatar.ru карточка: {edu_url}")
            if not out["vk"]:
                for vu in card.get("vk") or []:
                    verified = await fetch_vk_school_candidate(
                        client,
                        vu,
                        num=num,
                        title=title_for_vk,
                        known_phones=out["phones"],
                    )
                    if verified:
                        out["vk"] = verified["url"]
                        notes.append(f"ВК с edu.tatar: {out['vk']}")
                        break
        else:
            notes.append("edu.tatar кандидат отклонён (нет совпадения/телефонов)")

    # 2) VK candidates: heuristics + LLM + Maps, verify by body
    if not out["vk"] and num:
        vk_cands = _school_vk_guesses(num=num, title=title, city=city)
        for u in hints.get("vk") or []:
            s = str(u or "").strip()
            if s.startswith("http"):
                vk_cands.insert(0, s)
        maps = await scrape_maps_org_contacts(client, maps_url)
        vk_cands.extend(maps.get("vk") or [])
        for cand in _uniq(vk_cands, 14):
            verified = await fetch_vk_school_candidate(
                client,
                cand,
                num=num,
                title=title_for_vk,
                known_phones=out["phones"],
            )
            if not verified:
                continue
            out["vk"] = verified["url"]
            if not out["phones"]:
                for p in verified.get("phones") or []:
                    if p not in out["phones"]:
                        out["phones"].append(p)
            if not out["site"] and verified.get("sites"):
                host = (urlparse(verified["sites"][0]).netloc or "").lower()
                if "uslugi." not in host:
                    out["site"] = verified["sites"][0]
            notes.append(f"ВК подтверждён ({verified.get('via')}): {out['vk']}")
            break

    # 3) official site: confirm + scrape phone/email/vk
    site_hint = out.get("site") or str(hints.get("site") or "").strip()
    if site_hint.startswith("http"):
        try:
            resp = await client.get(site_hint, timeout=14.0)
            text = resp.text or ""
            blob = text[:50_000].lower().replace("ё", "е")
            ok = resp.status_code < 400 and (
                not num or num in blob or any(w in blob for w in ("школ", "гимназ", "лицей", "мбоу"))
            )
            if ok:
                out["site"] = site_hint.split("?")[0].rstrip("/")
                notes.append(f"сайт: {out['site']}")
                for p in (_norm_phone(x) for x in _PHONE_RE.findall(text)):
                    if p and p not in out["phones"]:
                        out["phones"].append(p)
                for em in re.findall(
                    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text
                ):
                    if em.lower() not in {e.lower() for e in out["emails"]}:
                        out["emails"].append(em)
                if not out["vk"]:
                    for vu in re.findall(
                        r"https?://(?:www\.)?vk\.(?:com|ru)/[A-Za-z0-9._/-]+", text
                    ):
                        verified = await fetch_vk_school_candidate(
                            client,
                            vu.split("?")[0],
                            num=num,
                            title=title_for_vk,
                            known_phones=out["phones"],
                        )
                        if verified:
                            out["vk"] = verified["url"]
                            notes.append(f"ВК с сайта: {out['vk']}")
                            break
        except Exception as exc:
            notes.append(f"сайт fetch: {exc}")

    out["phones"] = _uniq(out["phones"], 5)
    out["emails"] = _uniq(out["emails"], 5)
    out["notes"] = notes
    return out
