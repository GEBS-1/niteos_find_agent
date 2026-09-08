from __future__ import annotations

import asyncio
import base64
import html as htmllib
import logging
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

log = logging.getLogger(__name__)

_PHONE_RE = re.compile(
    r"(?:(?:\+7|8)[\s\-\u00a0]*\(?(?:\d{3})\)?[\s\-\u00a0]*\d{3}[\s\-\u00a0]*\d{2}[\s\-\u00a0]*\d{2})"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_BAD_HOST = (
    "duckduckgo.",
    "google.",
    "yandex.",
    "bing.",
    "vk.com/images",
    "2gis.",
    "facebook.",
    "wikipedia.",
    "youtube.",
    "rusprofile.",
    "list-org.",
    "checko.",
    "sbis.",
    "saby.",
    "kontur.",
    "nalog.",
    "avito.",
    "hh.ru",
    "youla.",
    "wildberries.",
    "bokep",
    "porn",
    "porno",
    "xxx",
    "sex",
    "casino",
    "bet",
)

# Hosts that match generic words from industrial company names — never treat as company site.
# Hosts of famous global brands — never attach to unrelated Russian SMEs.
_GLOBAL_BRAND_CORES = {
    "nvidia",
    "apple",
    "microsoft",
    "google",
    "amazon",
    "meta",
    "tesla",
    "intel",
    "amd",
    "samsung",
    "huawei",
    "xiaomi",
    "netflix",
    "spotify",
}

_GENERIC_SITE_HOSTS = {
    "zavod.ru",
    "zavod.rf",
    "xn--80aal6aj.xn--p1ai",  # завод.рф (approx — also match by core)
    "factory.ru",
    "prom.ru",
    "sklad.ru",
    "sklady.ru",
    "proizvodstvo.ru",
}

_BRAND_PUBLIC_SOURCES = {
    "фикс прайс": [
        {
            "title": "Сайт сети",
            "url": "https://fix-price.com/",
            "hint": "адреса магазинов и клиентский сайт",
            "kind": "site",
        },
        {
            "title": "Инвесторы Fix Price",
            "url": "https://investors.fix-price.ru/",
            "hint": "корпоративные контакты и раскрытие",
            "kind": "site",
            "phone": "+7 (499) 009-01-41",
            "email": "investors@fix-price.ru",
        },
        {
            "title": "Пресс-центр Fix Price",
            "url": "https://media.fix-price.com/",
            "hint": "новости, PR-контакты, развитие сети",
            "kind": "site",
            "email": "pr@fix-price.ru",
        },
        {
            "title": "Telegram · Fix Price",
            "url": "https://t.me/fixprice_russia",
            "hint": "публичный канал сети, сверить перед контактом",
            "kind": "telegram",
        },
    ],
    "fix price": [
        {
            "title": "Сайт сети",
            "url": "https://fix-price.com/",
            "hint": "адреса магазинов и клиентский сайт",
            "kind": "site",
        },
        {
            "title": "Инвесторы Fix Price",
            "url": "https://investors.fix-price.ru/",
            "hint": "корпоративные контакты и раскрытие",
            "kind": "site",
            "phone": "+7 (499) 009-01-41",
            "email": "investors@fix-price.ru",
        },
        {
            "title": "Пресс-центр Fix Price",
            "url": "https://media.fix-price.com/",
            "hint": "новости, PR-контакты, развитие сети",
            "kind": "site",
            "email": "pr@fix-price.ru",
        },
        {
            "title": "Telegram · Fix Price",
            "url": "https://t.me/fixprice_russia",
            "hint": "публичный канал сети, сверить перед контактом",
            "kind": "telegram",
        },
    ],
}

_STOP_TOKENS = {
    "завод",
    "завода",
    "заводы",
    "фабрика",
    "фабрики",
    "пром",
    "промка",
    "промышленный",
    "промышленная",
    "промышленное",
    "группа",
    "холдинг",
    "компания",
    "компании",
    "общество",
    "предприятие",
    "производство",
    "торговый",
    "торговая",
    "дом",
    "центр",
    "сервис",
    "плюс",
    "рус",
    "русская",
    "российский",
    "склад",
    "склады",
    "логистика",
    "логистический",
    "строительный",
    "строительная",
    "инвест",
    "инвестиции",
    "регион",
    "область",
    "город",
}


def _clean_company_name(name: str) -> str:
    text = (name or "").strip()
    text = re.sub(
        r"^(ООО|АО|ПАО|ЗАО|ОАО|НАО|ИП)\s*[«\"']?\s*",
        "",
        text,
        flags=re.I,
    )
    return text.strip(" «»\"'") or (name or "").strip()


def _city_from_address(address: str) -> str:
    address = address or ""
    for pattern in (
        r"г\.?\s*([А-ЯЁA-Z][а-яёa-z\-]+(?:[\s\-][А-ЯЁA-Z][а-яёa-z\-]+)?)",
        r"город\s+([А-ЯЁA-Z][а-яёa-z\-]+(?:[\s\-][А-ЯЁA-Z][а-яёa-z\-]+)?)",
    ):
        m = re.search(pattern, address)
        if m:
            return m.group(1)
    return ""


def _norm_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        return None
    return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"


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


def _site_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith("http"):
        return "https://" + raw.lstrip("/")
    return raw


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^\wА-Яа-яЁё0-9]+", (text or "").lower()) if len(t) >= 2]


def _distinctive_tokens(text: str) -> list[str]:
    out: list[str] = []
    for t in _tokens(text):
        if t in _STOP_TOKENS:
            continue
        if len(t) >= 4 or (len(t) >= 2 and t.isalpha()):
            out.append(t)
    return _uniq(out, 8)


def _brand_public_sources(*texts: str) -> list[dict[str, str]]:
    haystack = " ".join(texts).lower().replace("ё", "е")
    out: list[dict[str, str]] = []
    for key, items in _BRAND_PUBLIC_SOURCES.items():
        if key.replace("ё", "е") not in haystack:
            continue
        for item in items:
            out.append({k: str(v) for k, v in item.items()})
    return out


def _host_core(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""
    return host.split(":")[0]


def _is_generic_site_host(url: str) -> bool:
    host = _host_core(url)
    if not host:
        return True
    core = host.split(".")[0]
    if core in _GLOBAL_BRAND_CORES:
        return True
    if host in _GENERIC_SITE_HOSTS:
        return True
    core = host.split(".")[0]
    if core in _STOP_TOKENS or core in {"zavod", "factory", "prom", "sklad", "sklady", "proizvodstvo"}:
        return True
    # Punycode .рф industrial directories often contain "zavod"/"prom" in decoded form
    if "zavod" in host or host.endswith(".xn--p1ai") and core in {"xn--80aal6aj", "xn--80aalb4ai"}:
        return True
    return False


def _host_ok(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return bool(host) and not any(bad in host for bad in _BAD_HOST)


def _url_mentions_identity(url: str, needles: list[str], inn: str = "") -> bool:
    low = unquote_url(url).lower()
    if inn and inn in low:
        return True
    return any(n and n.lower() in low for n in needles)


def _safe_search_candidate(url: str, needles: list[str], inn: str = "") -> bool:
    """Only fetch arbitrary search results when the URL itself matches this company."""
    if not url or not _host_ok(url) or _is_generic_site_host(url):
        return False
    return _url_mentions_identity(url, needles, inn)


def _found(
    value: str | None,
    *,
    status: str | None = None,
    hint: str = "",
) -> dict[str, str]:
    value = (value or "").strip()
    if value:
        out = {"status": status or "найдено", "value": value}
        if hint:
            out["hint"] = hint
        return out
    return {"status": "нет", "value": ""}


async def _telegram_profile_ok(client: httpx.AsyncClient, url: str) -> bool:
    """True when t.me page looks like a real public profile/channel (not empty invite)."""
    if not _is_telegram_url(url):
        return False
    try:
        resp = await client.get(url, timeout=12.0)
    except Exception:
        return False
    if resp.status_code >= 400 or not resp.text:
        return False
    low = resp.text.lower()
    # Broken / missing username pages
    if "if you have telegram" in low and "tgme_page_title" not in low:
        return False
    if "tgme_page_title" in low or "tgme_username_link" in low:
        return True
    # Some public pages still usable
    return "telegram" in low and len(resp.text) > 800


async def _whatsapp_link_ok(client: httpx.AsyncClient, url: str) -> bool:
    """Only confirms the link opens — cannot prove the number is registered on WA.

    Use only for links harvested from site/VK, never for invented wa.me from phone.
    """
    if not _is_whatsapp_url(url):
        return False
    try:
        resp = await client.head(url, timeout=10.0, follow_redirects=True)
        if resp.status_code < 400:
            return True
    except Exception:
        pass
    try:
        resp = await client.get(url, timeout=12.0, follow_redirects=True)
        return resp.status_code < 400
    except Exception:
        return False


def _is_vk_url(url: str) -> bool:
    host = _host_core(url)
    ok_hosts = {
        "vk.com",
        "vk.ru",
        "m.vk.com",
        "m.vk.ru",
    }
    if host not in ok_hosts and not host.endswith(".vk.com") and not host.endswith(".vk.ru"):
        return False
    low = url.lower()
    if any(x in low for x in ("share.php", "login", "away.php", "/images/", "ads.php")):
        return False
    return True


def _is_vk_person_url(url: str) -> bool:
    """Personal profile (id123 / screen name), not club/public/company page."""
    if not _is_vk_url(url):
        return False
    try:
        path = (urlparse(url).path or "").strip("/")
    except Exception:
        return False
    if not path or "/" in path:
        return False
    low = path.lower()
    if low.startswith(
        ("club", "public", "event", "app", "video", "wall", "topic", "album", "market")
    ):
        return False
    # Reject LLM placeholders / obviously fake numeric ids
    fake_ids = {
        "123456",
        "1234567",
        "12345678",
        "123456789",
        "111111",
        "1111111",
        "000000",
        "999999",
        "12345",
        "1",
        "12",
        "123",
        "1234",
    }
    m_id = re.fullmatch(r"id(\d+)", low)
    if m_id:
        digits = m_id.group(1)
        if digits in fake_ids or len(digits) < 5:
            return False
        # Sequential / repeated digits (123456, 1111111, 121212)
        if len(set(digits)) <= 2 and len(digits) <= 8:
            return False
        if digits in {"1234567890"[: len(digits)], "9876543210"[: len(digits)]}:
            return False
        return True
    if re.fullmatch(r"\d+", low):
        if low in fake_ids or len(low) < 5:
            return False
        return True
    # Brand/org screen names are not LPR
    if any(
        x in low
        for x in (
            "arena",
            "stadium",
            "official",
            "school",
            "школа",
            "fc_",
            "fk_",
            "club",
            "kazan",
        )
    ):
        return False
    return bool(re.fullmatch(r"[a-zA-Z0-9._]+", path))


async def _verify_vk_lpr_for_fio(
    client: httpx.AsyncClient,
    url: str,
    fio: str,
    *,
    title: str = "",
    snippet: str = "",
) -> bool:
    """Accept personal VK only if FIO tokens appear on the page, URL, or SERP snippet."""
    if not _is_vk_person_url(url):
        return False
    if not _looks_like_person_fio(fio):
        return False
    needles = _distinctive_tokens(fio)
    if len(needles) < 2:
        return False
    if _url_has_needles(url, needles):
        return True
    blob = f"{title} {snippet}".lower().replace("ё", "е")
    if blob.strip():
        hits = sum(1 for n in needles if n and n in blob)
        if hits >= min(2, len(needles)):
            return True
    need = min(2, len(needles))
    return await _page_mentions(client, url, needles[:need])


async def _search_vk_by_fio(
    client: httpx.AsyncClient,
    person: str,
    *,
    city: str = "",
    llm: Any | None = None,
) -> tuple[str, list[str]]:
    """Search personal VK by FIO. Returns (best_url_or_empty, candidate_urls)."""
    from app.websearch import web_search

    if not _looks_like_person_fio(person):
        return "", []
    queries = [
        f'"{person}" ВК',
        f'"{person}" ВКонтакте',
        f'"{person}" site:vk.com',
        f'"{person}" vk.com/id',
    ]
    parts = person.split()
    if len(parts) >= 2:
        short = f"{parts[0]} {parts[1]}"
        queries.append(f'"{short}" ВК')
        queries.append(f'"{short}" ВКонтакте')
        queries.append(f'"{short}" site:vk.com')
    if city:
        queries.insert(0, f'"{person}" {city} ВК')
        queries.insert(1, f'"{person}" {city} ВКонтакте')
    candidates: list[str] = []
    best = ""
    for q in queries[:4]:
        try:
            hits = await web_search(client, q, num=8)
        except Exception:
            hits = []
        # Ignore junk CDN/home pages from blocked search HTML
        hits = [
            h
            for h in hits
            if "vk.com" in str(h.get("link") or "").lower()
            or "vk.ru" in str(h.get("link") or "").lower()
        ]
        for hit in hits:
            url = str(hit.get("link") or "").split("?")[0]
            if not _is_vk_person_url(url):
                continue
            candidates.append(url)
            if best:
                continue
            if await _verify_vk_lpr_for_fio(
                client,
                url,
                person,
                title=str(hit.get("title") or ""),
                snippet=str(hit.get("snippet") or ""),
            ):
                best = url
        if best:
            break

    # Paid RouterAI web — only if HUNT_LLM_WEB=1 (default off: free Yandex/Serper only)
    from app.cost_guard import llm_web_enabled

    if (
        not best
        and llm_web_enabled()
        and llm is not None
        and getattr(llm, "available", False)
    ):
        try:
            data = await llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Найди личный профиль ВКонтакте человека по ФИО. "
                            "Ответь JSON {\"vk_lpr\":\"https://vk.com/id…\",\"why\":\"\"}. "
                            "Только реальный найденный URL. Не выдумывай id. "
                            "Если не нашёл — {\"vk_lpr\":\"\",\"why\":\"не найдено\"}."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"ФИО: {person}\nГород: {city or '—'}\n"
                            "Ищи как в Google/Яндекс: «ФИО ВКонтакте», «ФИО site:vk.com»."
                        ),
                    },
                ],
                max_tokens=250,
                web=True,
                web_max_results=10,
                search_prompt=(
                    f"Найди личный профиль ВКонтакте человека «{person}»"
                    + (f" в городе {city}" if city else "")
                    + ". Ищи запросы: ФИО ВКонтакте, ФИО site:vk.com, ФИО vk.com/id. "
                    "Верни только персональные страницы, не паблики компаний."
                ),
            )
            url = str((data or {}).get("vk_lpr") or "").strip().split("?")[0]
            cite_urls = [
                str(c.get("link") or "")
                for c in ((data or {}).get("_citations") or [])
                if isinstance(c, dict)
            ]
            for cand in [url, *cite_urls]:
                cand = str(cand or "").strip().split("?")[0]
                if not _is_vk_person_url(cand):
                    continue
                candidates.append(cand)
                if best:
                    continue
                # Prefer page/SERP FIO match; VK often login-walls so soft-accept
                # numeric personal ids from the web plugin for the exact FIO query.
                if await _verify_vk_lpr_for_fio(client, cand, person):
                    best = cand
                elif re.search(r"/id(\d{6,12})$", cand):
                    best = cand
        except Exception:
            pass

    # Optional VK API users.search (needs user token with search scope)
    if not best:
        api_best, api_cands = await _vk_api_search_by_fio(client, person, city=city)
        candidates.extend(api_cands)
        if api_best:
            best = api_best

    return best, _uniq(candidates, 8)


async def _vk_api_search_by_fio(
    client: httpx.AsyncClient,
    person: str,
    *,
    city: str = "",
) -> tuple[str, list[str]]:
    """VK users.search when VK_USER_TOKEN / VK_ACCESS_TOKEN is set."""
    import os

    token = (
        os.getenv("VK_USER_TOKEN", "").strip()
        or os.getenv("VK_ACCESS_TOKEN", "").strip()
        or os.getenv("VK_TOKEN", "").strip()
    )
    if not token or not _looks_like_person_fio(person):
        return "", []
    params = {
        "q": person,
        "count": 10,
        "fields": "city,screen_name",
        "access_token": token,
        "v": "5.199",
    }
    try:
        resp = await client.get("https://api.vk.com/method/users.search", params=params, timeout=20.0)
        data = resp.json() if resp.content else {}
    except Exception:
        return "", []
    items = ((data.get("response") or {}).get("items") or []) if isinstance(data, dict) else []
    needles = _distinctive_tokens(person)
    cands: list[str] = []
    best = ""
    for row in items:
        if not isinstance(row, dict):
            continue
        uid = row.get("id")
        if not uid:
            continue
        url = f"https://vk.com/id{uid}"
        if not _is_vk_person_url(url):
            continue
        cands.append(url)
        blob = f"{row.get('first_name','')} {row.get('last_name','')} {row.get('screen_name','')}".lower()
        hits = sum(1 for n in needles if n and n in blob.replace("ё", "е"))
        city_name = str(((row.get("city") or {}) if isinstance(row.get("city"), dict) else {}).get("title") or "")
        city_ok = (not city) or (city.lower().replace("ё", "е") in city_name.lower().replace("ё", "е"))
        if hits >= min(2, len(needles)) and city_ok and not best:
            best = url
        elif hits >= min(2, len(needles)) and not best:
            best = url
    return best, cands


def _looks_like_person_fio(text: str) -> bool:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    if len(t) < 5 or len(t) > 80:
        return False
    low = t.lower().replace("ё", "е")
    # Whole-token org markers only (not substrings like «зао» inside «Заудатович»)
    org_tokens = {
        "ооо",
        "ао",
        "пао",
        "зао",
        "мбоу",
        "муп",
        "гбу",
        "мбу",
        "инн",
        "ип",
    }
    parts_low = [p.strip(".,;") for p in low.replace("«", " ").replace("»", " ").replace('"', " ").split() if p]
    if any(p in org_tokens for p in parts_low):
        return False
    if "«" in t or "»" in t or '"' in t:
        return False
    # Pure job title without a person name
    postish = (
        "генеральный директор",
        "директор",
        "руководитель",
        "председатель",
        "управляющий",
        "ио ",
        "врио ",
    )
    if any(low == p or low.startswith(p + " ") for p in postish) and not re.search(
        r"[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,3}", t
    ):
        return False
    parts = [p for p in t.replace("—", " ").replace("-", " ").split() if p]
    if len(parts) < 2 or len(parts) > 5:
        return False
    # At least two Cyrillic/Latin name tokens
    name_tokens = [
        p
        for p in parts
        if re.fullmatch(r"[A-Za-zА-Яа-яЁё-]{2,}", p)
        and p.lower()
        not in {
            "генеральный",
            "директор",
            "руководитель",
            "председатель",
            "управляющий",
            "ио",
            "врио",
        }
    ]
    return len(name_tokens) >= 2


def _director_people(party: dict[str, Any], fio: str) -> list[str]:
    """Real person names for VK search — never company/job-title stubs."""
    people: list[str] = []

    def add(name: str) -> None:
        n = re.sub(r"\s+", " ", str(name or "").strip())
        # Strip trailing post after em-dash
        if "—" in n:
            left, right = n.split("—", 1)
            if _looks_like_person_fio(left) and not _looks_like_person_fio(right):
                n = left.strip()
            elif _looks_like_person_fio(right) and not _looks_like_person_fio(left):
                n = right.strip()
        if _looks_like_person_fio(n) and n not in people:
            people.append(n)

    add(fio)
    add(str(party.get("management") or ""))
    for m in party.get("managers") or []:
        if isinstance(m, str):
            add(m.split("·")[0].strip())
        elif isinstance(m, dict):
            add(str(m.get("name") or m.get("fio") or ""))
    for f in party.get("founders") or []:
        add(str(f or "").split("·")[0].strip())
    for row in party.get("founders_detail") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").upper() == "LEGAL":
            continue
        add(str(row.get("name") or ""))
    return people[:5]


def _is_telegram_url(url: str) -> bool:
    host = _host_core(url)
    if host not in {"t.me", "telegram.me", "telegram.org"} and not host.endswith(".t.me"):
        return False
    low = url.lower()
    if any(x in low for x in ("/s/", "share", "login")):
        return False
    return True


def _is_whatsapp_url(url: str) -> bool:
    host = _host_core(url)
    low = url.lower()
    if "whatsapp.com" in host or host == "wa.me" or "api.whatsapp" in host:
        return "share" not in low
    return False


def _is_max_url(url: str) -> bool:
    host = _host_core(url)
    return host in {"max.ru", "max.me"} or host.endswith(".max.ru") or host.endswith(".max.me")


def _extract_social_links(html: str) -> dict[str, list[str]]:
    """Pull messenger / social URLs from page HTML (footer, contacts block)."""
    text = html or ""
    found: dict[str, list[str]] = {
        "vk_company": [],
        "telegram": [],
        "whatsapp": [],
        "max": [],
    }
    for raw in re.findall(r"""href\s*=\s*['"]([^'"]+)['"]""", text, flags=re.I):
        url = htmllib.unescape(raw.strip())
        if not url.startswith("http"):
            continue
        if _is_vk_url(url):
            found["vk_company"].append(url)
        elif _is_telegram_url(url):
            found["telegram"].append(url)
        elif _is_whatsapp_url(url):
            found["whatsapp"].append(url)
        elif _is_max_url(url):
            found["max"].append(url)
    for raw in re.findall(r"https?://[^\s\"'<>]+", text, flags=re.I):
        url = htmllib.unescape(raw.rstrip(".,;)"))
        if _is_vk_url(url):
            found["vk_company"].append(url)
        elif _is_telegram_url(url):
            found["telegram"].append(url)
        elif _is_whatsapp_url(url):
            found["whatsapp"].append(url)
        elif _is_max_url(url):
            found["max"].append(url)
    return {k: _uniq(v, 8) for k, v in found.items()}


def _pick_messenger(links: list[str], needles: list[str], *, kind: str) -> str:
    ranked: list[tuple[int, str]] = []
    for url in links:
        ok = {
            "vk": _is_vk_url,
            "tg": _is_telegram_url,
            "wa": _is_whatsapp_url,
            "max": _is_max_url,
        }.get(kind, lambda _u: False)
        if not ok(url):
            continue
        score = 1 + (5 if _url_has_needles(url, needles) else 0)
        ranked.append((score, url))
    ranked.sort(key=lambda x: -x[0])
    for score, url in ranked:
        if needles and score < 6:
            continue
        return url
    return ranked[0][1] if ranked else ""


def _url_has_needles(url: str, needles: list[str]) -> bool:
    low = unquote_url(url).lower()
    return any(n and n.lower() in low for n in needles)


def unquote_url(url: str) -> str:
    from urllib.parse import unquote

    return unquote(url or "")


def _pick_link(links: list[str], needles: list[str], prefer_hosts: tuple[str, ...] = ()) -> str:
    """Legacy helper — prefer strict pickers below for VK/TG/site."""
    ranked: list[tuple[int, str]] = []
    for url in links:
        host = urlparse(url).netloc.lower()
        score = 0
        if prefer_hosts and any(h in host for h in prefer_hosts):
            score += 5
        low = url.lower()
        for n in needles:
            if n and n.lower() in low:
                score += 2
        if score:
            ranked.append((score, url))
    ranked.sort(key=lambda x: -x[0])
    if ranked:
        return ranked[0][1]
    return ""


def _is_smb(party: dict[str, Any], company: str) -> bool:
    """Regional SME — easier social/LPR rules than federal chains."""
    emp = party.get("employee_count")
    if isinstance(emp, int):
        return emp <= 200
    low = (company or "").lower()
    if any(
        x in low
        for x in (
            "холдинг",
            "группа компан",
            "федеральн",
            "российск",
            "пao ",
            "пао ",
            "ао ",
            "газпром",
            "сбер",
            "лукойл",
            "x5",
            "озон",
            "ozon",
            "магнит",
            "агроторг",
        )
    ):
        return False
    return True


def _pick_social(
    links: list[str],
    needles: list[str],
    *,
    kind: str,
    relaxed: bool = False,
) -> str:
    """VK/Telegram only: never return a regular website, even if name tokens match."""
    ranked: list[tuple[int, str]] = []
    for url in links:
        if kind == "vk" and not _is_vk_url(url):
            continue
        if kind == "tg" and not _is_telegram_url(url):
            continue
        score = 1
        if _url_has_needles(url, needles):
            score += 5
        ranked.append((score, url))
    ranked.sort(key=lambda x: -x[0])
    min_score = 6 if needles and not relaxed else 1
    for score, url in ranked:
        if needles and score < min_score:
            continue
        return url
    if relaxed and ranked:
        return ranked[0][1]
    return ""


async def _page_mentions(
    client: httpx.AsyncClient, url: str, needles: list[str], inn: str = ""
) -> bool:
    try:
        resp = await client.get(_site_url(url), timeout=10.0)
    except Exception:
        return False
    if resp.status_code >= 400 or not resp.text:
        return False
    text = resp.text[:100_000].lower()
    if inn and inn in text:
        return True
    hits = sum(1 for n in needles if n and n.lower() in text)
    need = 1 if len(needles) <= 1 else min(2, len(needles))
    return hits >= need


async def _site_belongs(
    client: httpx.AsyncClient,
    url: str,
    distinctive: list[str],
    inn: str,
    *,
    trusted_inn_source: bool = False,
) -> bool:
    if not url or not _host_ok(url) or _is_generic_site_host(url):
        return False
    host = _host_core(url)
    # Marketplace / encyclopedia leftovers
    if any(x in host for x in ("wikipedia.", "wikidata.", "youtube.", "rutube.")):
        return False
    core = host.split(".")[0]
    if core in _GLOBAL_BRAND_CORES and distinctive:
        if not any(t in host for t in distinctive):
            return False
    if trusted_inn_source and inn:
        # List-Org page already matched INN — accept unless generic directory host.
        return True
    if distinctive and any(t in host for t in distinctive):
        return True
    if not distinctive:
        return False
    return await _page_mentions(client, url, distinctive, inn=inn)


CITY_SLUG = {
    "москва": "moscow",
    "санкт-петербург": "spb",
    "петербург": "spb",
    "казань": "kazan",
    "самара": "samara",
    "екатеринбург": "ekaterinburg",
    "новосибирск": "novosibirsk",
    "челябинск": "chelyabinsk",
    "нижний": "n_novgorod",
    "краснодар": "krasnodar",
    "уфа": "ufa",
    "ростов": "rostov",
    "воронеж": "voronezh",
    "пермь": "perm",
    "красноярск": "krasnoyarsk",
    "тюмень": "tyumen",
    "ижевск": "izhevsk",
    "ярославль": "yaroslavl",
    "тольятти": "togliatti",
    "барнаул": "barnaul",
    "иркутск": "irkutsk",
    "хабаровск": "khabarovsk",
    "владивосток": "vladivostok",
    "оренбург": "orenburg",
    "томск": "tomsk",
    "кемерово": "kemerovo",
    "рязань": "ryazan",
    "астрахань": "astrakhan",
    "пенза": "penza",
    "липецк": "lipetsk",
    "киров": "kirov",
    "чебоксары": "cheboksary",
    "калининград": "kaliningrad",
    "тула": "tula",
    "сочи": "sochi",
}


def _unwrap_bing(url: str) -> str:
    url = htmllib.unescape(url or "")
    if url.startswith("/ck/"):
        url = "https://www.bing.com" + url
    if "bing.com/ck/" not in url:
        return url
    raw = (parse_qs(urlparse(url).query).get("u") or [""])[0]
    if not raw.startswith("a1"):
        return url
    pad = raw[2:] + "=" * ((4 - len(raw[2:]) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(pad).decode("utf-8", "replace")
    except Exception:
        return url


def _norm_vk_url(url: str) -> str:
    url = (url or "").split("?")[0].rstrip("/")
    url = url.replace("://m.vk.com", "://vk.com").replace("://m.vk.ru", "://vk.ru")
    return url


def _vk_slug_guesses(*labels: str) -> list[str]:
    """Best-effort latin slug candidates from RU object/company labels."""
    table = str.maketrans(
        {
            "а": "a",
            "б": "b",
            "в": "v",
            "г": "g",
            "д": "d",
            "е": "e",
            "ё": "e",
            "ж": "zh",
            "з": "z",
            "и": "i",
            "й": "y",
            "к": "k",
            "л": "l",
            "м": "m",
            "н": "n",
            "о": "o",
            "п": "p",
            "р": "r",
            "с": "s",
            "т": "t",
            "у": "u",
            "ф": "f",
            "х": "h",
            "ц": "ts",
            "ч": "ch",
            "ш": "sh",
            "щ": "sch",
            "ъ": "",
            "ы": "y",
            "ь": "",
            "э": "e",
            "ю": "yu",
            "я": "ya",
        }
    )
    out: list[str] = []
    for label in labels:
        raw = re.sub(r'^(тц|трц|торговый центр)\s+', "", (label or "").strip(), flags=re.I)
        raw = re.sub(r'[«»"\']', "", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        if len(raw) < 3:
            continue
        low = raw.lower().replace("ё", "е")
        latin = low.translate(table)
        compact = re.sub(r"[^a-z0-9]+", "", latin)
        unders = re.sub(r"[^a-z0-9]+", "_", latin).strip("_")
        for slug in (
            unders,
            f"{unders}_kazan",
            f"{unders}_kzn",
            f"{compact}kzn" if len(compact) >= 4 else "",
            f"tc_{unders}" if len(unders) >= 4 else "",
            compact if len(compact) >= 6 else "",
        ):
            if slug and 4 <= len(slug) <= 32 and slug not in {"port", "shop", "mall", "market", "kazan"}:
                out.append(slug)
    return _uniq(out, 12)


async def _llm_suggest_vk_urls(
    llm: Any,
    *,
    company: str,
    obj_title: str,
    city: str,
) -> list[str]:
    if llm is None or not getattr(llm, "available", False):
        return []
    prompt = (
        "Найди вероятные публичные группы ВКонтакте для объекта/компании. "
        "Верни JSON {\"urls\":[\"https://vk.com/slug\", ...]} максимум 4 ссылки. "
        "Только vk.com или vk.ru, без пояснений. Если не уверен — [].\n"
        f"Объект: {obj_title or '—'}\nКомпания: {company or '—'}\nГород: {city or '—'}"
    )
    try:
        data = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": "Ты помощник по поиску официальных групп ВК торговых объектов.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=220,
        )
    except Exception:
        return []
    urls = data.get("urls") if isinstance(data, dict) else None
    if not isinstance(urls, list):
        return []
    out: list[str] = []
    for u in urls:
        s = _norm_vk_url(str(u or "").strip())
        if _is_vk_url(s):
            out.append(s)
    return _uniq(out, 4)


async def _brave_links(client: httpx.AsyncClient, query: str) -> list[str]:
    """Brave Search HTML — works for RU queries when Bing/DDG are poisoned/rate-limited."""
    if not (query or "").strip():
        return []
    links: list[str] = []
    try:
        resp = await client.get(
            "https://search.brave.com/search",
            params={"q": query, "source": "web"},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=18.0,
        )
    except Exception:
        return []
    if resp.status_code >= 400 or not resp.text:
        return []
    html = resp.text
    for raw in re.findall(
        r'class="result[^"]*"[^>]*>[\s\S]{0,400}?href="(https?://[^"]+)"',
        html,
        flags=re.I,
    ):
        url = htmllib.unescape(raw).split("&amp;")[0]
        if url.startswith("http") and _host_ok(url):
            links.append(url)
    for raw in re.findall(r'href="(https?://(?:m\.)?vk\.(?:com|ru)/[^"?#]+)', html, flags=re.I):
        url = htmllib.unescape(raw).split("?")[0].rstrip("/")
        # Prefer desktop host for downstream fetchers
        url = url.replace("://m.vk.com", "://vk.com").replace("://m.vk.ru", "://vk.ru")
        if _is_vk_url(url):
            links.append(url)
    for raw in re.findall(r'href="(https?://[^"]+)"', html):
        url = htmllib.unescape(raw)
        if any(
            bad in url.lower()
            for bad in (
                "brave.com",
                "brave.cloud",
                "youtube.com/watch",
                "accounts.google",
            )
        ):
            continue
        if _is_vk_url(url):
            url = url.split("?")[0].rstrip("/")
            url = url.replace("://m.vk.com", "://vk.com").replace("://m.vk.ru", "://vk.ru")
            links.append(url)
            continue
        if url.startswith("http") and _host_ok(url):
            links.append(url)
            if len(links) >= 24:
                break
    return _uniq(links, 12)


async def _ddg_links(client: httpx.AsyncClient, query: str) -> list[str]:
    """DuckDuckGo HTML search — may 202/challenge under rate limits."""
    if not (query or "").strip():
        return []
    links: list[str] = []
    try:
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
            timeout=18.0,
        )
    except Exception:
        return []
    if resp.status_code >= 400 or not resp.text:
        return []
    if resp.status_code == 202 or "anomaly" in (resp.text or "").lower():
        return []
    html = resp.text
    for raw in re.findall(r'uddg=([^&\"\']+)', html):
        url = unquote(raw)
        if url.startswith("http") and _host_ok(url):
            links.append(url)
    for raw in re.findall(
        r'class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"', html, flags=re.I
    ):
        url = unquote(htmllib.unescape(raw))
        if "duckduckgo.com" in url and "uddg=" in url:
            m = re.search(r"uddg=([^&]+)", url)
            if m:
                url = unquote(m.group(1))
        if url.startswith("http") and _host_ok(url):
            links.append(url)
    for raw in re.findall(
        r"https?://(?:m\.)?vk\.(?:com|ru)/[a-zA-Z0-9._/-]+", html
    ):
        if _host_ok(raw) or _is_vk_url(raw):
            links.append(raw.split("?")[0])
    return _uniq(links, 12)


async def _bing_links(client: httpx.AsyncClient, query: str) -> list[str]:
    """Web search: Serper API (if key) → Brave → DuckDuckGo → Bing."""
    try:
        from app.websearch import serper_api_key, serper_search

        if serper_api_key():
            hits = await serper_search(client, query, num=10)
            links = [h["link"] for h in hits if h.get("link")]
            if links:
                return _uniq(links, 12)
    except Exception:
        pass
    links = await _brave_links(client, query)
    if len(links) >= 3:
        return links
    links.extend(await _ddg_links(client, query))
    links = _uniq(links, 12)
    if len(links) >= 4:
        return links
    try:
        resp = await client.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "ru"},
        )
    except Exception:
        return links
    if resp.status_code >= 400:
        return links
    for raw in re.findall(r"<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"", resp.text, flags=re.I):
        url = _unwrap_bing(raw)
        if url.startswith("http") and _host_ok(url):
            links.append(url)
    for cite in re.findall(r"<cite[^>]*>(.*?)</cite>", resp.text, flags=re.I | re.S):
        text = re.sub(r"<[^>]+>", "", cite).strip()
        text = text.replace(" › ", "/").replace(" ? ", "/")
        text = text.split()[0] if text else ""
        if text and not text.startswith("http"):
            text = "https://" + text
        if text.startswith("http") and _host_ok(text):
            links.append(text)
    return _uniq(links, 12)


def _image_url_ok(url: str) -> bool:
    low = (url or "").lower()
    if not low.startswith("http"):
        return False
    if any(x in low for x in ("logo", "favicon", "icon", "sprite", "avatar", "placeholder", "1x1")):
        return False
    if any(x in low for x in (".svg", ".gif")):
        return False
    if not any(x in low for x in (".jpg", ".jpeg", ".png", ".webp", "image", "photo", "upload")):
        return False
    host = _host_core(url)
    return bool(host) and not any(
        bad in host for bad in ("google.", "bing.", "yandex.", "vk.com/images")
    )


def _clean_image_url(raw: str) -> str:
    raw = htmllib.unescape(raw or "").strip()
    raw = raw.replace("\\/", "/")
    try:
        raw = raw.encode("utf-8").decode("unicode_escape")
    except Exception:
        pass
    return raw


async def _bing_image_urls(
    client: httpx.AsyncClient,
    query: str,
    *,
    limit: int = 6,
) -> list[str]:
    urls: list[str] = []
    try:
        resp = await client.get(
            "https://www.bing.com/images/search",
            params={"q": query, "setlang": "ru"},
            timeout=14.0,
        )
    except Exception:
        return []
    if resp.status_code >= 400 or not resp.text:
        return []
    patterns = (
        r'"murl"\s*:\s*"([^"]+)"',
        r'&quot;murl&quot;\s*:\s*&quot;([^&]+)&quot;',
        r"murl&quot;:&quot;([^&]+)&quot;",
    )
    for pat in patterns:
        for raw in re.findall(pat, resp.text, flags=re.I):
            url = _clean_image_url(raw)
            if _image_url_ok(url):
                urls.append(url)
        if urls:
            break
    return _uniq(urls, limit)


async def _checko_party_facts(
    client: httpx.AsyncClient, inn: str
) -> dict[str, Any]:
    """Founders (with INN) + headcount from Checko when DaData omits them."""
    out: dict[str, Any] = {
        "founders_detail": [],
        "founders": [],
        "employee_count": None,
        "url": "",
        "director": "",
        "revenue": None,
        "profit": None,
        "expense": None,
        "finance_year": "",
    }
    if not inn:
        return out
    page_url = ""
    html = ""
    try:
        search = await client.get(
            "https://checko.ru/search",
            params={"query": inn},
            timeout=16.0,
        )
    except Exception:
        search = None
    # Prefer final company page URL (search often lands on /company/slug-ogrn)
    if search is not None and search.status_code < 400:
        html = search.text or ""
        page_url = str(search.url)
        if "/company/" in page_url and "select" not in page_url:
            pass  # already on company card
        else:
            m_id = re.search(r"/company/(?:[a-z0-9\-]+-)?(\d{10,15})", page_url)
            if m_id:
                page_url = f"https://checko.ru/company/{m_id.group(1)}"
            else:
                m = re.search(
                    rf'href="(/company/[^"]+)"[^>]*>[\s\S]{{0,400}}?{re.escape(inn)}',
                    html,
                    flags=re.I,
                )
                if not m:
                    m = re.search(r'href="(/company/[a-z0-9\-]+-\d+)"', html, flags=re.I)
                if m:
                    page_url = "https://checko.ru" + m.group(1).split("?")[0]
        page_url = re.sub(
            r"/(taxes|founders|finance|connections|timeline|requisites)/?$",
            "",
            page_url,
        )
        try:
            if "select" in page_url or not html or inn not in html:
                page = await client.get(page_url, timeout=16.0)
                if page.status_code < 400:
                    html = page.text or ""
                    page_url = str(page.url)
        except Exception:
            pass
    if not html or (inn not in html and "Руководитель" not in html):
        return out
    page_url = re.sub(
        r"/(taxes|founders|finance|connections|timeline|requisites)/?$",
        "",
        page_url,
    )
    out["url"] = page_url
    # Director first — Checko cards put Руководитель + /person/INN
    director = ""
    m_dir = re.search(
        r'Руководитель[\s\S]{0,600}?href="/person/(\d{10,12})"[^>]*>([^<]{3,120})</a>',
        html,
        flags=re.I,
    )
    if m_dir:
        cand = htmllib.unescape(re.sub(r"\s+", " ", m_dir.group(2))).strip()
        if _looks_like_person_fio(cand):
            director = cand
    if not director:
        m_dir = re.search(
            r'href="/person/(\d{10,12})"[^>]*>([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,3})</a>',
            html,
        )
        if m_dir:
            cand = htmllib.unescape(re.sub(r"\s+", " ", m_dir.group(2))).strip()
            if _looks_like_person_fio(cand):
                director = cand
    if director:
        out["director"] = director

    founders: list[dict[str, Any]] = []
    for m in re.finditer(
        r'Учредитель[\s\S]{0,320}?href="/person/(\d{10,12})"[^>]*>([^<]{3,120})</a>',
        html,
        flags=re.I,
    ):
        finn = m.group(1)
        name = htmllib.unescape(re.sub(r"\s+", " ", m.group(2))).strip()
        if not name or finn == inn:
            continue
        founders.append(
            {
                "name": name,
                "inn": finn,
                "share": "",
                "type": "PHYSICAL" if len(finn) == 12 else "LEGAL",
                "role": "учредитель / выгодоприобретатель",
                "label": f"{name} · ИНН {finn}",
            }
        )
    if not founders:
        m = re.search(
            r"единственн\w*\s+учредитель\s*[—\-–]\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,3})",
            html,
            flags=re.I,
        )
        if m:
            name = m.group(1).strip()
            pm = re.search(
                rf'href="/person/(\d{{10,12}})"[^>]*>{re.escape(name)}</a>',
                html,
                flags=re.I,
            )
            finn = pm.group(1) if pm else ""
            founders.append(
                {
                    "name": name,
                    "inn": finn,
                    "share": "",
                    "type": "PHYSICAL" if len(finn) == 12 else "",
                    "role": "учредитель / выгодоприобретатель",
                    "label": f"{name}" + (f" · ИНН {finn}" if finn else ""),
                }
            )
    seen: set[str] = set()
    uniq_f: list[dict[str, Any]] = []
    for f in founders:
        key = str(f.get("inn") or f.get("name") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        uniq_f.append(f)
    out["founders_detail"] = uniq_f[:6]
    out["founders"] = [f["label"] for f in uniq_f[:6]]
    m_emp = re.search(
        r"среднесписочн\w*\s+численност\w*[^0-9]{0,80}(\d{1,5})\s*человек",
        html,
        flags=re.I,
    )
    if not m_emp:
        m_emp = re.search(
            r"ССЧ работников[^0-9]{0,40}(\d{1,5})\s*человек",
            html,
            flags=re.I,
        )
    if m_emp:
        try:
            out["employee_count"] = int(m_emp.group(1))
        except ValueError:
            pass
    # Finance snippets on Checko company card (тыс / млн ₽) — free, no LLM
    def _parse_money_block(label: str) -> tuple[int | None, str]:
        m = re.search(
            rf"{label}[^0-9\-]{{0,80}}(-?\d[\d\s]{{0,20}})\s*(тыс|млн|млрд)?",
            html,
            flags=re.I,
        )
        if not m:
            return None, ""
        try:
            num = int(re.sub(r"\s+", "", m.group(1)))
        except ValueError:
            return None, ""
        unit = (m.group(2) or "тыс").lower()
        # Store as thousands of rubles (same as FNS BFO)
        if unit.startswith("млрд"):
            num *= 1_000_000
        elif unit.startswith("млн"):
            num *= 1_000
        return num, ""

    rev, _ = _parse_money_block(r"Выручка")
    profit, _ = _parse_money_block(r"(?:Чистая\s+)?прибыль")
    expense, _ = _parse_money_block(r"Расход")
    if rev is not None:
        out["revenue"] = rev
    if profit is not None:
        out["profit"] = profit
    if expense is not None:
        out["expense"] = expense
    m_year = re.search(r"финансов\w*\s+показател\w*[^0-9]{0,40}(20\d{2})", html, flags=re.I)
    if m_year:
        out["finance_year"] = m_year.group(1)
    if not out.get("director"):
        for pat in (
            r'(?:Руководитель|Генеральный\s+директор|Директор)[\s\S]{0,280}?'
            r'href="/person/\d{10,12}"[^>]*>([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,3})</a>',
            r'(?:Руководитель|Генеральный\s+директор)\s*[—\-–:]\s*'
            r'([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,3})',
        ):
            m_dir = re.search(pat, html, flags=re.I)
            if m_dir:
                cand = htmllib.unescape(re.sub(r"\s+", " ", m_dir.group(1))).strip()
                if _looks_like_person_fio(cand):
                    out["director"] = cand
                    break
    return out


def _wa_me_from_phone(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 11 and d[0] in "78":
        d = "7" + d[1:]
    elif len(d) == 10:
        d = "7" + d
    if len(d) == 11 and d.startswith("7"):
        return f"https://wa.me/{d}"
    return ""


async def _enrich_people_channels(
    client: httpx.AsyncClient,
    *,
    party: dict[str, Any],
    company: str,
    city: str,
    inn: str,
    fio: str,
    phones: list[str],
    track_phone,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Open-registry research: director/founders → VK / messengers / phones."""
    out: dict[str, Any] = {
        "vk_lpr": "",
        "vk_company": "",
        "site": "",
        "telegram": "",
        "whatsapp": "",
        "web_lpr": "",
        "notes": [],
        "people": [],
    }
    people = _director_people(party, fio)
    out["people"] = people[:5]

    building = ""
    obj = party.get("object") if isinstance(party.get("object"), dict) else {}
    building = str(obj.get("title") or "").strip()

    if (
        llm is not None
        and getattr(llm, "available", False)
        and inn
    ):
        from app.cost_guard import llm_web_enabled

        if not llm_web_enabled():
            out["notes"].append(
                "LLM-web выключен (HUNT_LLM_WEB=0) — контакты только из реестров и бесплатного поиска"
            )
        else:
            try:
                people_hint = ", ".join(people) if people else (fio or "—")
                data = await llm.chat_json(
                    [
                        {
                            "role": "system",
                            "content": (
                                "Исследовательский поиск по открытым реестрам РФ "
                                "(ЕГРЮЛ-зеркала, официальные сайты, ВК). Ответь JSON: "
                                '{"director":"","phones":[],"vk_lpr":"","vk":"",'
                                '"site":"","telegram":"","whatsapp":"",'
                                '"beneficiaries":[],"why":""}. '
                                "director — ФИО человека из ЕГРЮЛ (три слова), не должность. "
                                "vk_lpr — только найденный личный профиль этого ФИО "
                                "(реальный https://vk.com/id… или vk.ru/id…); "
                                "НЕ выдумывай id, НЕ подставляй примеры, НЕ группы компании. "
                                "Пусто если не нашёл. Группу компании только в vk."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"ИНН {inn}\nКомпания: {company}\nГород: {city}\n"
                                f"Здание: {building or '—'}\n"
                                f"ФИО для поиска в ВК (обязательно по этим людям): {people_hint}\n"
                                "Сначала уточни ФИО директора, затем найди его личный ВК "
                                "запросом как «ФИО ВКонтакте» / «ФИО vk.com». "
                                "Без ФИО — vk_lpr оставь пустым."
                            ),
                        },
                    ],
                    max_tokens=500,
                    web=True,
                    web_max_results=8,
                )
                if isinstance(data, dict):
                    for p in data.get("phones") or []:
                        track_phone(str(p), "RouterAI/реестры")
                    director = str(data.get("director") or "").strip()
                    if _looks_like_person_fio(director) and director not in people:
                        people.insert(0, director)
                        out["people"] = people[:5]
                    for key in ("vk_lpr", "telegram", "whatsapp"):
                        val = str(data.get(key) or "").strip()
                        if not val.startswith("http"):
                            continue
                        if key == "vk_lpr":
                            if _is_vk_person_url(val) and people:
                                out["vk_lpr"] = val.split("?")[0]
                        elif not out.get(key):
                            out[key] = val
                    site = str(data.get("site") or "").strip()
                    if site.startswith("http"):
                        out["site"] = site.split("?")[0].rstrip("/")
                    vk_co = str(data.get("vk") or data.get("vk_company") or "").strip()
                    if vk_co.startswith("http") and "vk." in vk_co and not _is_vk_person_url(vk_co):
                        out["vk_company"] = vk_co.split("?")[0]
                    if data.get("beneficiaries") and not party.get("founders"):
                        party["founders"] = [
                            str(x) for x in (data.get("beneficiaries") or [])[:5] if x
                        ]
                    if data.get("why"):
                        out["notes"].append(f"LLM люди: {str(data.get('why'))[:100]}")
            except Exception as exc:
                out["notes"].append(f"LLM люди: {exc}")

    # Open pages: org site / maps card → phones + social links (generic, no venue hardcode)
    pages: list[str] = []
    if out.get("site"):
        base = str(out["site"]).rstrip("/")
        pages.append(base)
        for suffix in ("/kontakty", "/contacts", "/contact", "/o-kompanii", "/about"):
            pages.append(base + suffix)
    maps = str(obj.get("maps_yandex") or "")
    if "/org/" in maps:
        pages.append(maps)
    for page in _uniq(pages, 6):
        try:
            resp = await client.get(page, timeout=14.0)
        except Exception:
            continue
        if resp.status_code >= 400 or not resp.text:
            continue
        for raw in re.findall(
            r"\+7\D{0,3}\d{3}\D{0,3}\d{3}\D{0,3}\d{2}\D{0,3}\d{2}",
            resp.text,
        ):
            track_phone(raw, f"страница:{page[:40]}")
        if not out.get("vk_company"):
            for vu in re.findall(
                r"https?://(?:www\.)?vk\.(?:com|ru)/[A-Za-z0-9._/-]+", resp.text
            ):
                if any(x in vu for x in ("share", "widget", "away.php", "login")):
                    continue
                out["vk_company"] = vu.split("?")[0]
                out["notes"].append(f"ВК с сайта: {page[:50]}")
                break
        if not out.get("whatsapp"):
            for wu in re.findall(
                r"https?://(?:wa\.me|api\.whatsapp\.com)/[^\s\"'<>]+",
                resp.text,
                flags=re.I,
            ):
                out["whatsapp"] = wu.split("?")[0]
                out["notes"].append("WhatsApp-ссылка найдена на сайте")
                break
        if not out.get("telegram"):
            for tu in re.findall(
                r"https?://(?:t\.me|telegram\.me)/[A-Za-z0-9_]+", resp.text, flags=re.I
            ):
                out["telegram"] = tu.split("?")[0]
                out["notes"].append("Telegram-ссылка найдена на сайте")
                break

    for person in people[:3]:
        best, cands = await _search_vk_by_fio(client, person, city=city, llm=llm)
        for u in cands:
            if u not in (out.get("_vk_cands") or []):
                pass
        if best:
            out["vk_lpr"] = best
            out["notes"].append(f"ВК ЛПР по ФИО «{person}»: {best}")
            break
        if cands and not out["vk_lpr"]:
            # Try page verify on remaining candidates
            for u in cands:
                if await _verify_vk_lpr_for_fio(client, u, person):
                    out["vk_lpr"] = u
                    out["notes"].append(f"ВК ЛПР по ФИО «{person}»: {u}")
                    break
        if out["vk_lpr"]:
            break

    # Drop LLM vk_lpr if it doesn't match any known FIO
    if out["vk_lpr"] and people:
        ok_any = False
        for person in people[:3]:
            if await _verify_vk_lpr_for_fio(client, out["vk_lpr"], person):
                ok_any = True
                break
        if not ok_any:
            out["notes"].append(f"ВК ЛПР отклонён (не подтверждён по ФИО): {out['vk_lpr']}")
            out["vk_lpr"] = ""
    elif out["vk_lpr"] and not people:
        out["notes"].append("ВК ЛПР отклонён: нет ФИО для проверки")
        out["vk_lpr"] = ""
    elif people and not out["vk_lpr"]:
        out["notes"].append(
            f"ВК ЛПР: не найден по ФИО «{people[0]}» (поиск + проверка)"
        )

    return out


async def _list_org_contacts(
    client: httpx.AsyncClient, inn: str
) -> tuple[str, list[str], list[str], str]:
    """Return (site, phones, emails, company_page_url) from List-Org by INN."""
    if not inn:
        return "", [], [], ""
    try:
        resp = await client.get(
            "https://www.list-org.com/search",
            params={"type": "inn", "val": inn},
        )
    except Exception:
        return "", [], [], ""
    if resp.status_code >= 400:
        return "", [], [], ""
    company_ids = re.findall(r"href=['\"]/company/(\d+)['\"]", resp.text)
    for cid in _uniq(company_ids, 5):
        page_url = f"https://www.list-org.com/company/{cid}"
        try:
            page = await client.get(page_url)
        except Exception:
            continue
        if page.status_code >= 400 or inn not in page.text:
            continue
        sites = re.findall(
            r"class=['\"][^'\"]*site[^'\"]*['\"][^>]*>(https?://[^<]+)</a>",
            page.text,
            flags=re.I,
        )
        phones: list[str] = []
        for raw in re.findall(r"/phone/(\d[\d\-]+)", page.text):
            digits = re.sub(r"\D", "", raw)
            if len(digits) == 10:
                digits = "7" + digits
            norm = _norm_phone(digits)
            if norm:
                phones.append(norm)
        emails: list[str] = []
        for block in re.findall(r"mailto:([^\"'\s>]+)", page.text, flags=re.I):
            for part in block.split(","):
                email = part.strip()
                if "@" in email and not any(
                    bad in email.lower() for bad in ("example.com", "list-org")
                ):
                    emails.append(email)
        site = _site_url(sites[0]) if sites else ""
        return site, _uniq(phones, 5), _uniq(emails, 5), page_url
    return "", [], [], f"https://www.list-org.com/search?type=inn&val={quote_plus(inn)}"


async def _alive(client: httpx.AsyncClient, url: str) -> bool:
    try:
        resp = await client.get(_site_url(url), timeout=10.0)
        return resp.status_code < 400
    except Exception:
        return False


async def _harvest_site(
    client: httpx.AsyncClient, url: str
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    try:
        resp = await client.get(_site_url(url), timeout=12.0)
    except Exception:
        return [], [], {}
    if resp.status_code >= 400 or not resp.text:
        return [], [], {}
    text = resp.text[:200_000]
    phones = []
    for match in _PHONE_RE.findall(text):
        norm = _norm_phone(match)
        if norm:
            phones.append(norm)
    emails = [
        e
        for e in _EMAIL_RE.findall(text)
        if not any(bad in e.lower() for bad in ("example.com", "sentry", "wixpress", "cloudflare"))
    ]
    social = _extract_social_links(text)
    return _uniq(phones, 5), _uniq(emails, 5), social


async def _phones_from_2gis(client: httpx.AsyncClient, company: str, city: str) -> tuple[str, str]:
    """Returns (phone, maps_url)."""
    slug = CITY_SLUG.get(city.lower()) if city else ""
    q = " ".join(x for x in (company, city) if x)
    if slug:
        url = f"https://2gis.ru/{slug}/search/{quote_plus(q)}"
    else:
        url = f"https://2gis.ru/search/{quote_plus(q)}"
    try:
        resp = await client.get(url, timeout=15.0)
    except Exception:
        return "", url
    if resp.status_code >= 400:
        return "", url
    phones = []
    for raw in re.findall(r"\+7\d{10}", resp.text):
        norm = _norm_phone(raw)
        if norm:
            phones.append(norm)
    phones = _uniq(phones, 5)
    return (phones[0] if phones else ""), url


async def enrich_contacts(
    party: dict[str, Any],
    client: httpx.AsyncClient | None = None,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Agent-2 online check + optional Agent-3 LLM gate."""
    own = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=18.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            },
        )
    try:
        company = _clean_company_name(str(party.get("name") or ""))
        fio_raw = str(party.get("management") or "").strip()
        people0 = _director_people(party, fio_raw)
        fio = people0[0] if people0 else fio_raw
        requested_city = str(party.get("requested_city") or "").strip()
        city = requested_city or _city_from_address(str(party.get("address") or ""))
        search_phrase = str(party.get("search_phrase") or "").strip()
        inn = str(party.get("inn") or "").strip()
        distinctive = _distinctive_tokens(company)
        fio_needles = _distinctive_tokens(fio)
        smb = _is_smb(party, company)
        management_label = str(
            party.get("management_label") or party.get("management") or ""
        ).strip()
        management_post = str(party.get("management_post") or "").strip()

        phones = _uniq([_norm_phone(p) or p for p in (party.get("phones") or []) if p])
        emails = _uniq([str(e) for e in (party.get("emails") or []) if e])
        sites = _uniq([_site_url(s) for s in (party.get("sites") or []) if s])
        phone_sources: list[dict[str, str]] = []

        def _track_phone(raw: str, source: str) -> None:
            norm = _norm_phone(raw) or (raw or "").strip()
            if not norm:
                return
            for item in phone_sources:
                if _digits_phone(item.get("value") or "") == _digits_phone(norm):
                    if source not in (item.get("source") or ""):
                        item["source"] = f"{item['source']}, {source}"
                    return
            phone_sources.append({"value": norm, "source": source})
            if norm not in phones:
                phones.append(norm)

        def _digits_phone(p: str) -> str:
            d = re.sub(r"\D", "", p or "")
            if len(d) == 11 and d[0] in "78":
                return "7" + d[1:]
            if len(d) == 10:
                return "7" + d
            return d

        for p in list(phones):
            _track_phone(p, "ЕГРЮЛ/DaData")

        checks: list[str] = []
        site_url = ""
        vk_company = ""
        vk_lpr = ""
        telegram = ""
        whatsapp = ""
        max_link = ""
        web_lpr = ""
        site_candidates: list[str] = []
        vk_candidates: list[str] = []
        vk_lpr_candidates: list[str] = []
        tg_candidates: list[str] = []
        wa_candidates: list[str] = []
        max_candidates: list[str] = []
        web_lpr_candidates: list[str] = []
        brand_sources = _brand_public_sources(search_phrase, company)
        list_org_url = (
            f"https://www.list-org.com/search?type=inn&val={quote_plus(inn)}" if inn else ""
        )

        def _merge_social(social: dict[str, list[str]]) -> None:
            nonlocal vk_company, telegram, whatsapp, max_link
            for u in social.get("vk_company") or []:
                vk_candidates.append(u)
                if not vk_company:
                    vk_company = u
            for u in social.get("telegram") or []:
                tg_candidates.append(u)
                if not telegram:
                    telegram = u
            for u in social.get("whatsapp") or []:
                wa_candidates.append(u)
                if not whatsapp:
                    whatsapp = u
            for u in social.get("max") or []:
                max_candidates.append(u)
                if not max_link:
                    max_link = u

        for cand in sites:
            site_candidates.append(cand)
            if await _site_belongs(client, cand, distinctive, inn):
                site_url = cand
                checks.append("Сайт из реестра")
                break
        sites = [site_url] if site_url else []

        if inn:
            lo_site, lo_phones, lo_emails, lo_url = await _list_org_contacts(client, inn)
            if lo_url:
                list_org_url = lo_url
            if lo_site:
                site_candidates.append(lo_site)
            if lo_site and not site_url:
                if await _site_belongs(
                    client, lo_site, distinctive, inn, trusted_inn_source=True
                ):
                    site_url = lo_site
                    sites = _uniq([lo_site] + sites)
                    checks.append("Сайт с List-Org")
                else:
                    checks.append("Сайт List-Org отклонён (чужой/общий)")
            if lo_phones:
                for p in lo_phones:
                    _track_phone(p, "List-Org")
                checks.append("Телефон с List-Org")
            if lo_emails:
                emails = _uniq(emails + lo_emails)
                checks.append("Email с List-Org")
            # Checko: founders + headcount + director FIO + finance when thin
            need_checko = (
                not (party.get("founders") or party.get("founders_detail"))
                or party.get("employee_count") in (None, "", 0)
                or not _looks_like_person_fio(fio)
                or party.get("revenue") is None
                or party.get("profit") is None
                or party.get("expense") is None
            )
            if need_checko:
                facts = await _checko_party_facts(client, inn)
                if facts.get("founders_detail") and not (
                    party.get("founders") or party.get("founders_detail")
                ):
                    party["founders_detail"] = facts["founders_detail"]
                    party["founders"] = facts.get("founders") or [
                        str(f.get("label") or "") for f in facts["founders_detail"]
                    ]
                    checks.append("Учредители / выгодоприобретатели с Checko")
                if facts.get("employee_count") and party.get("employee_count") in (
                    None,
                    "",
                    0,
                ):
                    party["employee_count"] = facts["employee_count"]
                    checks.append(
                        f"Среднесписочная численность с Checko: {facts['employee_count']}"
                    )
                if facts.get("url"):
                    party["_checko_url"] = facts["url"]
                if facts.get("revenue") is not None and party.get("revenue") is None:
                    party["revenue"] = facts["revenue"]
                    party["finance_source"] = "checko"
                    checks.append("Выручка с Checko")
                if facts.get("profit") is not None and party.get("profit") is None:
                    party["profit"] = facts["profit"]
                    party["finance_source"] = party.get("finance_source") or "checko"
                    checks.append("Прибыль с Checko")
                if facts.get("expense") is not None and party.get("expense") is None:
                    party["expense"] = facts["expense"]
                    party["finance_source"] = party.get("finance_source") or "checko"
                    checks.append("Расходы с Checko")
                if facts.get("finance_year") and not party.get("finance_year"):
                    party["finance_year"] = facts["finance_year"]
                director = str(facts.get("director") or "").strip()
                if director and _looks_like_person_fio(director):
                    if not _looks_like_person_fio(fio):
                        fio = director
                        party["management"] = director
                        party["management_label"] = (
                            f"{director}"
                            + (f" — {management_post}" if management_post else "")
                        )
                        management_label = party["management_label"]
                        fio_needles = _distinctive_tokens(fio)
                        checks.append(f"ФИО руководителя с Checko: {director}")
                    else:
                        party.setdefault("_people_extra", []).append(director)

            # Director / founders → соцсети и мессенджеры (открытые реестры + поиск)
            people_hit = await _enrich_people_channels(
                client,
                party=party,
                company=company,
                city=city,
                inn=inn,
                fio=fio,
                phones=phones,
                track_phone=_track_phone,
                llm=llm,
            )
            if people_hit.get("vk_lpr") and _is_vk_person_url(people_hit["vk_lpr"]):
                # Only keep if verified against FIO
                person_for_vk = fio
                extras = people_hit.get("people") or []
                verified = False
                for person in [person_for_vk, *extras][:4]:
                    if not _looks_like_person_fio(str(person or "")):
                        continue
                    if await _verify_vk_lpr_for_fio(
                        client, people_hit["vk_lpr"], str(person)
                    ):
                        vk_lpr = people_hit["vk_lpr"]
                        vk_lpr_candidates.append(vk_lpr)
                        checks.append(f"ВК ЛПР подтверждён по ФИО «{person}»")
                        verified = True
                        break
                if not verified:
                    checks.append(
                        f"ВК ЛПР кандидат отклонён (нет ФИО на странице): {people_hit['vk_lpr']}"
                    )
            if people_hit.get("people"):
                # Prefer real FIO list for later VK search
                for name in people_hit["people"]:
                    if _looks_like_person_fio(str(name)) and str(name) not in (
                        party.get("_people_extra") or []
                    ):
                        party.setdefault("_people_extra", []).append(str(name))
            if people_hit.get("notes"):
                for note in people_hit["notes"][:6]:
                    checks.append(str(note))
            if people_hit.get("vk_company") and not vk_company:
                vk_company = people_hit["vk_company"]
                vk_candidates.append(vk_company)
                checks.append("ВК компании из открытых источников")
            if people_hit.get("site") and not site_url:
                site_cand = str(people_hit["site"])
                site_candidates.append(site_cand)
                if await _site_belongs(
                    client, site_cand, distinctive, inn, trusted_inn_source=True
                ):
                    site_url = site_cand
                    sites = _uniq([site_cand] + sites)
                    checks.append("Сайт из открытых реестров/поиска")
            if people_hit.get("telegram") and not telegram:
                telegram = people_hit["telegram"]
                tg_candidates.append(telegram)
            if people_hit.get("whatsapp") and not whatsapp:
                # Only real harvested links — never invented from phone
                whatsapp = people_hit["whatsapp"]
                wa_candidates.append(whatsapp)
            if people_hit.get("web_lpr") and not web_lpr:
                web_lpr = people_hit["web_lpr"]
            for note in people_hit.get("notes") or []:
                checks.append(note)
        site_trusted = bool(site_url) and any(
            x in c for c in checks for x in ("List-Org", "реестра")
        )
        if site_url:
            open_cands = [site_url]
            if site_url.startswith("http://"):
                open_cands.append("https://" + site_url[len("http://") :])
            opened = False
            for cand in open_cands:
                if await _alive(client, cand):
                    site_url = cand
                    sites = _uniq([cand] + sites)
                    checks.append("Сайт открывается")
                    more_p, more_e, social = await _harvest_site(client, cand)
                    for p in more_p:
                        _track_phone(p, "сайт")
                    emails = _uniq(emails + more_e)
                    if social:
                        _merge_social(social)
                        checks.append("Соцсети с сайта")
                    opened = True
                    break
            if not opened:
                if site_trusted:
                    checks.append("Сайт в карточке есть, с сервера не открылся")
                else:
                    checks.append("Сайт не открылся")
                    site_url = ""

        obj_title = ""
        if isinstance(party.get("object"), dict):
            obj_title = str((party.get("object") or {}).get("title") or "").strip()

        # Schools (Тататарстан): edu.tatar.ru + verified VK — Bing often returns garbage for RU
        from app.school_contacts import enrich_school_contacts, is_school_context

        if is_school_context(title=obj_title, company=company):
            obj_meta = (
                party.get("object") if isinstance(party.get("object"), dict) else {}
            )
            school_hit = await enrich_school_contacts(
                client,
                title=obj_title or company,
                company=company,
                city=city,
                address=str(
                    obj_meta.get("address")
                    or party.get("object_address")
                    or party.get("address")
                    or ""
                ),
                maps_url=str(obj_meta.get("maps_yandex") or ""),
                llm=llm,
            )
            for p in school_hit.get("phones") or []:
                _track_phone(p, "edu.tatar/школа")
            if school_hit.get("emails"):
                emails = _uniq(emails + list(school_hit["emails"]))
                checks.append("Email школы (edu.tatar.ru)")
            if school_hit.get("site") and not site_url:
                site_url = school_hit["site"]
                sites = _uniq([site_url] + sites)
                checks.append("Сайт школы подтверждён")
            if school_hit.get("vk") and not vk_company:
                vk_company = school_hit["vk"]
                vk_candidates.append(vk_company)
                checks.append(f"ВК школы: {vk_company}")
            if school_hit.get("edu_url"):
                site_candidates.append(school_hit["edu_url"])
                if not site_url:
                    site_url = school_hit["edu_url"]
                    sites = _uniq([site_url] + sites)
                    checks.append("Карточка edu.tatar.ru как сайт")
            for note in school_hit.get("notes") or []:
                checks.append(note)

        if not site_url:
            await asyncio.sleep(0.25)
            site_search_qs = [f'"{company}" {city} официальный сайт'.strip()]
            if obj_title and any(
                w in obj_title.lower()
                for w in ("школ", "лицей", "гимнази", "мбоу", "маоу", "больниц")
            ):
                site_search_qs = [
                    f'"{obj_title}" {city} официальный сайт'.strip(),
                    f'"{obj_title}" {city} сайт'.strip(),
                    f"{obj_title} {city} edu".strip(),
                ] + site_search_qs
            accepted = ""
            for sq in site_search_qs[:3]:
                site_links = await _bing_links(client, sq)
                safe_site_links = [
                    u for u in site_links if _safe_search_candidate(u, distinctive, inn)
                ]
                # For schools also accept .edu / school-looking hosts even if company tokens weak
                if obj_title and "школ" in obj_title.lower():
                    for u in site_links:
                        host = (urlparse(u).netloc or "").lower()
                        if any(
                            h in host
                            for h in (".edu.", "edu.ru", "school", "sch", "obr.")
                        ) and u not in safe_site_links:
                            safe_site_links.append(u)
                site_candidates.extend(safe_site_links[:8])
                for cand in safe_site_links:
                    belongs = await _site_belongs(client, cand, distinctive, inn)
                    if not belongs and obj_title:
                        # School sites often use short names; check title tokens
                        title_toks = [
                            t
                            for t in re.findall(
                                r"[а-яa-z0-9]{3,}",
                                obj_title.lower().replace("ё", "е"),
                            )
                            if t not in {"школа", "лицей", "гимназия"}
                        ]
                        try:
                            resp = await client.get(cand, timeout=10.0)
                            blob = (resp.text or "")[:40_000].lower().replace("ё", "е")
                        except Exception:
                            blob = ""
                        if title_toks and any(t in blob for t in title_toks[:4]):
                            belongs = True
                        num_m = re.search(r"(?:№|n)\s*(\d{1,4})", obj_title.lower())
                        if num_m:
                            num = num_m.group(1)
                            if num and (
                                f"№{num}" in blob
                                or f"№ {num}" in blob
                                or f"школа {num}" in blob
                            ):
                                belongs = True
                    if not belongs:
                        continue
                    if await _alive(client, cand):
                        accepted = cand
                        break
                if accepted:
                    break
            if accepted:
                site_url = accepted
                sites = _uniq([accepted] + sites)
                checks.append("Сайт найден в поиске")
                more_p, more_e, social = await _harvest_site(client, accepted)
                for p in more_p:
                    _track_phone(p, "сайт (поиск)")
                emails = _uniq(emails + more_e)
                if social:
                    _merge_social(social)
                    checks.append("Соцсети с сайта")
            else:
                checks.append("Сайт: нет")

        if brand_sources:
            brand_phones: list[str] = []
            brand_emails: list[str] = []
            for item in brand_sources:
                phone = item.get("phone") or ""
                email = item.get("email") or ""
                if phone:
                    norm = _norm_phone(phone) or phone
                    brand_phones.append(norm)
                    _track_phone(norm, item.get("title") or "источник бренда")
                if email:
                    brand_emails.append(email)
            if brand_phones:
                phones = _uniq(brand_phones + phones)
                checks.append("Официальный телефон сети добавлен по бренду")
            if brand_emails:
                emails = _uniq(brand_emails + emails)
                checks.append("Официальный email сети добавлен по бренду")
            site_source = next(
                (item for item in brand_sources if item.get("kind") == "site"),
                None,
            )
            if site_source:
                site_candidates.append(site_source["url"])
                if not site_url:
                    site_url = site_source["url"]
                    sites = _uniq([site_url] + sites)
                    checks.append("Сайт сети добавлен по бренду")
            telegram_source = next(
                (item for item in brand_sources if item.get("kind") == "telegram"),
                None,
            )
            if telegram_source and not telegram:
                telegram = telegram_source["url"]
                tg_candidates.append(telegram)
                checks.append("Telegram сети добавлен по бренду (сверить)")

        await asyncio.sleep(0.3)
        # Simple searcher queries work best: «название ВК», «объект ВК город»
        short_co = re.sub(
            r'^(ООО|АО|ПАО|ЗАО|ИП|НАО|ОАО)\s*[«"\']?\s*',
            "",
            company or "",
            flags=re.I,
        )
        short_co = re.sub(r'[»"\']', "", short_co).strip() or company
        vk_queries = [
            f"{short_co} ВК".strip(),
            f"{short_co} ВК {city}".strip(),
            f"{short_co} вконтакте {city}".strip(),
            f'"{short_co}" site:vk.ru'.strip(),
            f'"{short_co}" site:vk.com'.strip(),
            f'"{company}" {city} vk.ru вконтакте'.strip(),
        ]
        if obj_title:
            vk_queries = [
                f"{obj_title} ВК".strip(),
                f"{obj_title} ВК {city}".strip(),
                f"{obj_title} вконтакте {city}".strip(),
                f'"{obj_title}" site:vk.ru'.strip(),
                f'"{obj_title}" site:vk.com'.strip(),
            ] + vk_queries
            num_m = re.search(r"(?:№|n)\s*(\d{1,4})", obj_title.lower())
            if num_m and any(w in obj_title.lower() for w in ("школ", "лицей", "гимнази")):
                num = num_m.group(1)
                vk_queries = [
                    f"школа №{num} {city} ВКонтакте".strip(),
                    f"школа {num} {city} вк".strip(),
                    f'"школа №{num}" {city} site:vk.com'.strip(),
                ] + vk_queries
        if smb:
            vk_queries.append(f"{short_co} {city} вконтакте группа")
            vk_queries.append(f"{short_co} vk.ru")
            vk_queries.append(f"{short_co} vk.com")
        vk_co_links: list[str] = []
        for q in vk_queries[:8]:
            vk_co_links.extend(await _bing_links(client, q))
            await asyncio.sleep(0.35)
        vk_co_links = _uniq(vk_co_links, 12)
        vk_queries.append(f"site:vk.com/club {short_co} {city}".strip())
        vk_queries.append(f"site:vk.com/public {short_co} {city}".strip())
        vk_queries.append(f"site:vk.ru {short_co} {city}".strip())
        for q in vk_queries[-3:]:
            vk_co_links.extend(await _bing_links(client, q))
            await asyncio.sleep(0.35)
        vk_co_links = _uniq(vk_co_links, 16)
        # Do NOT invent slug/LLM URLs as accept candidates — only real search hits
        # and links harvested from the company website (added later via evidence).
        prior_vk = [u for u in vk_co_links if _is_vk_url(u)]
        if not prior_vk:
            checks.append("ВК: поиск пуст — не подставляем угаданный slug")

        def _vk_rank_url(url: str) -> tuple[int, int]:
            path = urlparse(url).path.strip("/")
            score = 0
            if path.endswith(("kzn", "kazan")):
                score += 6
            if "_" in path:
                score += 3
            if len(path) >= 6:
                score += 2
            if path in {"port", "shop", "mall", "market"}:
                score -= 10
            return (-score, -len(path))

        # Prefer real VK urls from search only
        vk_co_links = _uniq(prior_vk + vk_co_links, 20)
        from app.vk_group import (
            extract_group_contacts_llm,
            fetch_vk_group,
            is_vk_group_url,
        )

        def _vk_label_match(page_title: str, *labels: str) -> bool:
            pt = (page_title or "").lower().replace("ё", "е")
            if not pt or pt in {"вконтакте | вконтакте", "вконтакте", "vk"}:
                return False
            pt_tokens = {t for t in re.findall(r"[a-zа-я0-9]{3,}", pt)}
            blob = " ".join(str(x or "").lower().replace("ё", "е") for x in labels)
            # Stadium aliases: Ак Барс Арена ↔ Казань Арена
            if ("арена" in pt or "arena" in pt) and (
                "арена" in blob or "стадион" in blob or "ак барс" in blob
            ):
                return True
            for label in labels:
                lab = (label or "").lower().replace("ё", "е")
                if not lab or len(lab) < 3:
                    continue
                if lab in pt or pt in lab:
                    return True
                lab_tokens = {t for t in re.findall(r"[a-zа-я0-9]{3,}", lab)}
                stop = {"ооо", "ао", "пао", "тц", "трц", "центр", "торговый", "компания"}
                overlap = (pt_tokens & lab_tokens) - stop
                if any(len(x) >= 4 for x in overlap):
                    return True
            return False

        def _vk_url_trusted(url: str) -> bool:
            """VK harvested from official site (note) — accept even if login-wall title."""
            return any(
                "ВК с сайта" in str(n) or "из открытых источников" in str(n)
                for n in checks
            ) and _is_vk_url(url)

        vk_co_links = [_norm_vk_url(u) for u in vk_co_links if u]
        vk_group_links = [u for u in vk_co_links if _is_vk_url(u) and is_vk_group_url(u)]

        def _vk_rank(url: str) -> tuple[int, int]:
            path = urlparse(url).path.strip("/")
            score = 0
            if path.endswith(("kzn", "kazan")):
                score += 6
            if "_" in path:
                score += 3
            if len(path) >= 6:
                score += 2
            if path in {"port", "shop", "mall", "market"}:
                score -= 5
            return (-score, -len(path))

        vk_candidates = sorted(
            vk_group_links[:12] or [u for u in vk_co_links if _is_vk_url(u)][:12],
            key=_vk_rank,
        )[:8]
        # Accept VK only after page fetch + title match to building/company
        if not vk_company:
            for cand in vk_candidates:
                if not _is_vk_url(cand):
                    continue
                parsed_try = await fetch_vk_group(client, cand)
                title_try = str(parsed_try.get("title") or "")
                if not parsed_try.get("ok"):
                    continue
                if _vk_label_match(title_try, obj_title, short_co, company):
                    vk_company = parsed_try.get("url") or cand
                    checks.append("ВК группа подтверждена по названию страницы")
                    break
                if distinctive and await _page_mentions(client, cand, distinctive, inn=inn):
                    vk_company = parsed_try.get("url") or cand
                    checks.append("ВК группа: страница упоминает компанию/ИНН")
                    break
        if vk_company and site_url and _host_core(vk_company) == _host_core(site_url):
            vk_company = ""
        vk_group_block: dict[str, Any] = {"status": "нет", "value": "", "contacts": []}
        vk_verified = False
        if vk_company and is_vk_group_url(vk_company):
            parsed = await fetch_vk_group(client, vk_company)
            title_low = str(parsed.get("title") or "").lower().strip()
            generic_wall = title_low in {"вконтакте | вконтакте", "вконтакте", "vk"} or (
                title_low.startswith("вконтакте") and len(title_low) < 24
            )
            title_ok = _vk_label_match(
                str(parsed.get("title") or ""), obj_title, short_co, company
            )
            # Schools: VK often login-walls the <title>; accept by body (№ + школа)
            school_body_ok = False
            if is_school_context(title=obj_title, company=company):
                from app.school_contacts import school_number, vk_html_matches_school

                num_s = school_number(obj_title) or school_number(company)
                try:
                    raw = await client.get(vk_company, timeout=12.0)
                    school_body_ok = bool(num_s) and vk_html_matches_school(
                        raw.text or "", num=num_s, title=obj_title
                    )
                except Exception:
                    school_body_ok = False
            if parsed.get("ok") and (
                (not generic_wall and title_ok)
                or school_body_ok
                or _vk_url_trusted(vk_company)
            ):
                vk_verified = True
                rows: list[dict[str, str]] = []
                if llm is not None and getattr(llm, "available", False):
                    rows = await extract_group_contacts_llm(
                        llm, company=company, inn=inn, group=parsed
                    )
                for p in parsed.get("phones") or []:
                    _track_phone(str(p), "ВК группа")
                for e in parsed.get("emails") or []:
                    if e not in emails:
                        emails.append(str(e))
                for site_cand in parsed.get("sites") or []:
                    cleaned = _site_url(str(site_cand))
                    if cleaned and not _is_generic_site_host(cleaned):
                        if not site_url:
                            site_url = cleaned
                            sites = _uniq([site_url] + sites)
                            checks.append("Сайт взят из ВК-группы")
                        elif cleaned not in sites:
                            sites = _uniq(sites + [cleaned])
                for link in parsed.get("links") or []:
                    if _is_telegram_url(link) and not telegram:
                        telegram = link
                        checks.append("Telegram из ВК-группы")
                    if _is_whatsapp_url(link) and not whatsapp:
                        whatsapp = link
                        checks.append("WhatsApp из ВК-группы")
                    if _is_max_url(link) and not max_link:
                        max_link = link
                vk_group_block = {
                    "status": "найдено",
                    "value": parsed.get("url") or vk_company,
                    "title": parsed.get("title") or "",
                    "description": (parsed.get("description") or "")[:400],
                    "contacts": rows,
                    "phones": parsed.get("phones") or [],
                    "emails": parsed.get("emails") or [],
                    "sites": parsed.get("sites") or [],
                }
                checks.append("ВК группа: страница разобрана")
                if school_body_ok and generic_wall:
                    checks.append("ВК школы подтверждён по содержимому страницы")
                if rows:
                    checks.append(f"ВК группа: {len(rows)} контакт(ов) для связи")
                else:
                    if _vk_url_trusted(vk_company):
                        vk_verified = True
                        vk_group_block = {
                            "status": "найдено",
                            "value": vk_company,
                            "title": str(parsed.get("title") or ""),
                            "description": "",
                            "contacts": [],
                            "phones": [],
                            "emails": [],
                            "sites": [],
                        }
                        checks.append("ВК группа: принята с официального сайта")
                    else:
                        # Drop unverified guess
                        vk_company = ""
                        checks.append(
                            "ВК кандидат отклонён: название страницы не совпало с зданием/УК"
                        )
        if vk_company and vk_verified:
            checks.append("ВК компании найден")
        elif vk_company and _vk_url_trusted(vk_company):
            vk_verified = True
            checks.append("ВК компании: подтверждён источником (сайт/реестр)")
        else:
            vk_company = ""
            checks.append("ВК компании: нет (без угадывания slug)")
        vk_guess = vk_company if vk_verified else ""  # only restore verified

        if fio or party.get("_people_extra"):
            await asyncio.sleep(0.3)
            search_people = []
            for name in [fio, *(party.get("_people_extra") or [])]:
                if _looks_like_person_fio(str(name or "")) and str(name) not in search_people:
                    search_people.append(str(name))
            if not search_people:
                search_people = _director_people(party, fio)
            if not search_people:
                checks.append("ВК ЛПР: нет — нет ФИО руководителя для поиска")
            vk_pe_links: list[str] = []
            for person in search_people[:2]:
                checks.append(f"ВК ЛПР: ищем по ФИО «{person}»")
                best, cands = await _search_vk_by_fio(client, person, city=city, llm=llm)
                vk_pe_links.extend(cands)
                if best and not vk_lpr:
                    vk_lpr = best
                    checks.append(
                        f"ВК ЛПР найден и проверен по ФИО «{person}»: {vk_lpr}"
                    )
            vk_pe_links = _uniq(vk_pe_links, 16)
            person_links = [u for u in vk_pe_links if _is_vk_person_url(u)]
            vk_lpr_candidates = _uniq(vk_lpr_candidates + person_links, 8)
            if not vk_lpr:
                for person in search_people[:2]:
                    for cand in person_links:
                        if await _verify_vk_lpr_for_fio(client, cand, person):
                            vk_lpr = cand.split("?")[0]
                            checks.append(
                                f"ВК ЛПР найден и проверен по ФИО «{person}»: {vk_lpr}"
                            )
                            break
                    if vk_lpr:
                        break
            if vk_lpr and _is_vk_person_url(vk_lpr):
                ok = False
                for person in search_people[:3]:
                    if await _verify_vk_lpr_for_fio(client, vk_lpr, person):
                        ok = True
                        break
                if not ok:
                    checks.append(f"ВК ЛПР сброшен после проверки ФИО: {vk_lpr}")
                    vk_lpr = ""
                else:
                    checks.append("ВК ЛПР: проверка ФИО пройдена")
            else:
                vk_lpr = ""
                if search_people:
                    checks.append("ВК ЛПР: нет подходящего профиля по ФИО")

            await asyncio.sleep(0.3)
            web_person = search_people[0] if search_people else fio
            from app.websearch import web_search_links
            web_links = await web_search_links(
                client, f'"{web_person}" "{company}" {city}'.strip(), num=8
            ) if web_person else []
            fio_needles = _distinctive_tokens(web_person) if web_person else fio_needles
            for cand in web_links:
                if site_url and _host_core(cand) == _host_core(site_url):
                    continue
                if _is_vk_url(cand) or _is_telegram_url(cand):
                    continue
                if not _host_ok(cand) or _is_generic_site_host(cand):
                    continue
                if not _url_mentions_identity(cand, distinctive + fio_needles, inn):
                    continue
                host = _host_core(cand)
                if any(x in host for x in ("rbc.ru", "forbes.ru", "wikipedia.", "wikidata.")):
                    if not distinctive:
                        continue
                try:
                    resp = await client.get(_site_url(cand), timeout=10.0)
                    text = (resp.text or "")[:100_000].lower()
                except Exception:
                    continue
                if resp.status_code >= 400 or not text:
                    continue
                fio_hits = sum(1 for n in fio_needles if n and n in text)
                co_hits = sum(1 for n in distinctive if n and n in text)
                if fio_hits < min(2, max(1, len(fio_needles))):
                    continue
                if distinctive and co_hits < 1 and (inn not in text):
                    continue
                if not distinctive and inn and inn not in text:
                    continue
                web_lpr_candidates.append(cand)
                if not web_lpr:
                    web_lpr = cand
            if web_lpr:
                checks.append("Упоминание ЛПР в сети найдено")
            else:
                checks.append("Упоминание ЛПР в сети: нет")
        else:
            checks.append("ЛПР в ЕГРЮЛ нет — соцсети ЛПР не искали")

        await asyncio.sleep(0.3)
        tg_links = await _bing_links(
            client, f'"{company}" {city} t.me telegram'.strip()
        )
        tg_candidates = [u for u in tg_links if _is_telegram_url(u)][:8]
        telegram = _pick_social(tg_links, distinctive, kind="tg")
        if not telegram and distinctive:
            for cand in tg_links:
                if not _is_telegram_url(cand):
                    continue
                if await _page_mentions(client, cand, distinctive, inn=inn):
                    telegram = cand
                    break
        if telegram and site_url and _host_core(telegram) == _host_core(site_url):
            telegram = ""
        if telegram:
            checks.append("Telegram найден")
        else:
            checks.append("Telegram: нет")

        await asyncio.sleep(0.3)
        wa_links = await _bing_links(
            client, f'"{company}" {city} whatsapp wa.me'.strip()
        )
        wa_candidates.extend([u for u in wa_links if _is_whatsapp_url(u)][:8])
        if not whatsapp:
            whatsapp = _pick_messenger(wa_links, distinctive, kind="wa")
        if whatsapp:
            checks.append("WhatsApp найден")
        else:
            checks.append("WhatsApp: нет")

        await asyncio.sleep(0.3)
        max_links = await _bing_links(
            client, f'"{company}" {city} max.ru мессенджер'.strip()
        )
        max_candidates.extend([u for u in max_links if _is_max_url(u)][:8])
        if not max_link:
            max_link = _pick_messenger(max_links, distinctive, kind="max")
        if max_link:
            checks.append("Max найден")
        else:
            checks.append("Max: нет")

        phone_2gis, maps_url = await _phones_from_2gis(client, company, city)
        if phone_2gis:
            _track_phone(phone_2gis, "2ГИС")
            checks.append("Телефон с 2ГИС (сверить)")
        # Extra open-web phone hunt by УК / object name
        if len(phones) < 2:
            phone_qs = [
                f"{short_co} телефон {city}".strip(),
                f"{obj_title} телефон {city}".strip() if obj_title else "",
                f"{short_co} контакты {city}".strip(),
            ]
            for pq in phone_qs:
                if not pq or len(pq) < 8:
                    continue
                for link in (await _bing_links(client, pq))[:6]:
                    if not _host_ok(link) and not _is_vk_url(link):
                        continue
                    try:
                        page = await client.get(link, timeout=12.0)
                    except Exception:
                        continue
                    if page.status_code >= 400:
                        continue
                    body = page.text or ""
                    low = body.lower()
                    # Only harvest phones from pages that clearly mention this company
                    if inn and inn not in body:
                        if not any(tok and tok.lower() in low for tok in distinctive[:4]):
                            continue
                    before = len(phones)
                    for raw in _PHONE_RE.findall(body):
                        digits = re.sub(r"\D", "", raw)
                        # Prefer RU numbers; skip short/foreign junk
                        if len(digits) < 11:
                            continue
                        if digits.startswith("7") and digits[1:4] in {
                            "044",
                            "050",
                            "063",
                            "067",
                            "068",
                            "095",
                            "096",
                            "097",
                            "098",
                            "099",
                        }:
                            continue
                        _track_phone(raw, f"поиск: {pq[:40]}")
                    if len(phones) > before:
                        checks.append("Телефон из открытого поиска по названию УК/объекта")
                        break
                if phones and any(
                    "поиск:" in str(x.get("source") or "") for x in phone_sources
                ):
                    break
        if not phones:
            checks.append("Телефон: нет")
        obj_meta = party.get("object") if isinstance(party.get("object"), dict) else {}
        map_name = (
            (obj_meta.get("title") or "").strip()
            or short_co
            or (search_phrase if search_phrase and len(search_phrase) > 3 else company)
        )
        map_addr = (obj_meta.get("address") or party.get("object_address") or "").strip()
        legal_addr = str(party.get("address") or "").strip()
        # Prefer street/house for the pin — never bare «торговый центр Казань»
        from app.objects import streetish_address as _streetish

        if not _streetish(map_addr) and _streetish(legal_addr):
            map_addr = legal_addr
        if _streetish(map_addr):
            map_query = f"{map_name} {map_addr}".strip()
        elif map_name and city and map_name.lower() not in {city.lower(), "торговый центр"}:
            map_query = f"{map_name} {city}".strip()
        else:
            map_query = f"{short_co or company} {city}".strip()
        maps_yandex = (obj_meta.get("maps_yandex") or "").strip()
        if (not maps_yandex) or ("text=" in maps_yandex and _streetish(map_addr)):
            maps_yandex = f"https://yandex.ru/maps/?text={quote_plus(map_query)}"
        maps_google = (obj_meta.get("maps_google") or "").strip() or (
            f"https://www.google.com/maps/search/?api=1&query={quote_plus(map_query)}"
        )
        if obj_meta.get("url_2gis"):
            maps_url = str(obj_meta.get("url_2gis") or maps_url)

        if phones and not whatsapp:
            checks.append(
                "WhatsApp: не показан — нет явной ссылки wa.me на сайте/ВК "
                "(из телефона не склеиваем)"
            )

        # Messenger presence checks (where possible without private APIs)
        whatsapp_hint = ""
        telegram_hint = ""
        if whatsapp:
            if await _whatsapp_link_ok(client, whatsapp):
                whatsapp_hint = "ссылка открывается; регистрацию номера WA публично не проверить"
                checks.append("WhatsApp: ссылка проверена (найдена в источниках)")
            else:
                checks.append("WhatsApp: ссылка не открылась — убираем")
                whatsapp = ""
        if telegram:
            if await _telegram_profile_ok(client, telegram):
                telegram_hint = "публичная страница Telegram открывается"
                checks.append("Telegram: страница проверена")
            else:
                checks.append("Telegram: страница пустая/не найдена — убираем")
                telegram = ""

        if vk_lpr and not _is_vk_person_url(vk_lpr):
            checks.append("ВК ЛПР: отклонён (это не личный профиль)")
            vk_lpr = ""

        presence = {
            "lpr": {
                "status": "найдено" if management_label else "нет",
                "value": management_label,
                "post": management_post,
                "source": "ЕГРЮЛ",
                "hint": "Руководитель по выписке — основной ЛПР для звонка",
            },
            "site": _found(site_url),
            "phone": _found(phones[0] if phones else ""),
            "email": _found(emails[0] if emails else ""),
            "vk_company": _found(vk_company),
            "vk_group": vk_group_block,
            "vk_lpr": _found(vk_lpr),
            "telegram": _found(telegram, hint=telegram_hint),
            "whatsapp": _found(whatsapp, hint=whatsapp_hint),
            "max": _found(max_link),
            "web_lpr": _found(web_lpr),
            "maps_2gis": {"status": "открыть", "value": maps_url},
            "maps_yandex": {"status": "открыть", "value": maps_yandex},
            "maps_google": {"status": "открыть", "value": maps_google},
            "checks": checks,
            "phone_sources": phone_sources[:8],
        }

        photos: list[str] = []
        address = str(party.get("address") or "")

        if llm is not None and getattr(llm, "available", False):
            from app.research import build_evidence, dedupe_urls

            traps = ["https://zavod.ru/"] if "завод" in company.lower() else []
            site_trusted = bool(site_url) and any(
                "List-Org" in c or "реестра" in c for c in (presence.get("checks") or [])
            )
            evidence_urls = dedupe_urls(
                [
                    site_url,
                    list_org_url,
                    vk_company,
                    vk_lpr,
                    telegram,
                    whatsapp,
                    max_link,
                    web_lpr,
                    maps_url,
                    maps_yandex,
                    *vk_candidates,
                    *tg_candidates,
                    *site_candidates,
                    *traps,
                ],
                limit=10,
            )
            evidence_urls = [
                u
                for u in evidence_urls
                if (
                    _is_vk_url(u)
                    or _is_telegram_url(u)
                    or _is_whatsapp_url(u)
                    or _is_max_url(u)
                    or "2gis." in _host_core(u)
                    or "yandex." in _host_core(u)
                    or "list-org." in _host_core(u)
                    or _safe_search_candidate(u, distinctive + fio_needles, inn)
                )
            ]
            snippets, _evidence_photos = await build_evidence(client, urls=evidence_urls, max_pages=6)
            if snippets:
                checks.append(f"Исследователь: прочитано страниц {len(snippets)}")
            presence["checks"] = checks

            from app.cost_guard import llm_verify_enabled

            if llm_verify_enabled():
                from app.verify import investigate_presence

                presence = await investigate_presence(
                    llm,
                    company=company,
                    inn=inn,
                    city=city,
                    address=address,
                    fio=fio,
                    presence=presence,
                    site_trusted=site_trusted,
                    phone_sources=phone_sources,
                    snippets=snippets,
                    is_smb=smb,
                    candidates={
                        "site": _uniq(site_candidates + traps, 8),
                        "vk_company": _uniq(vk_candidates, 6),
                        "vk_lpr": _uniq(vk_lpr_candidates, 6),
                        "telegram": _uniq(tg_candidates, 6),
                        "whatsapp": _uniq(wa_candidates, 6),
                        "max": _uniq(max_candidates, 6),
                        "web_lpr": _uniq(web_lpr_candidates, 6),
                    },
                )
            else:
                checks.append(
                    "LLM-проверка выключена (HUNT_LLM_VERIFY=0) — только подтверждённые поля"
                )
                presence["checks"] = checks
            site_url = (presence.get("site") or {}).get("value") or ""
            vk_company = (presence.get("vk_company") or {}).get("value") or ""
            # Restore only if it was verified earlier (vk_guess empty otherwise)
            if not vk_company and vk_guess:
                vk_company = vk_guess
                presence["vk_company"] = _found(vk_company)
                checks = list(presence.get("checks") or [])
                checks.append("ВК: сохранён проверенный после LLM")
                presence["checks"] = checks
            elif vk_company and vk_company != vk_guess:
                # LLM may invent a link — accept only after page title match
                parsed_llm = await fetch_vk_group(client, vk_company)
                if not (
                    parsed_llm.get("ok")
                    and _vk_label_match(
                        str(parsed_llm.get("title") or ""),
                        obj_title,
                        short_co,
                        company,
                    )
                ):
                    vk_company = ""
                    presence["vk_company"] = {"status": "нет", "value": ""}
                    checks = list(presence.get("checks") or [])
                    checks.append("ВК от LLM отклонён: страница не совпала с зданием/УК")
                    presence["checks"] = checks
                else:
                    presence["vk_company"] = _found(parsed_llm.get("url") or vk_company)
            elif not vk_company:
                presence["vk_company"] = {"status": "нет", "value": ""}
            vk_lpr = (presence.get("vk_lpr") or {}).get("value") or ""
            if vk_lpr:
                person_ok = False
                for person in [fio, *(party.get("_people_extra") or [])][:4]:
                    if _looks_like_person_fio(str(person or "")) and await _verify_vk_lpr_for_fio(
                        client, vk_lpr, str(person)
                    ):
                        person_ok = True
                        checks = list(presence.get("checks") or [])
                        checks.append(f"ВК ЛПР после LLM: подтверждён по ФИО «{person}»")
                        presence["checks"] = checks
                        break
                if not person_ok or not _is_vk_person_url(vk_lpr):
                    checks = list(presence.get("checks") or [])
                    checks.append(f"ВК ЛПР после LLM отклонён: {vk_lpr}")
                    presence["checks"] = checks
                    vk_lpr = ""
                    presence["vk_lpr"] = {"status": "нет", "value": ""}
            telegram = (presence.get("telegram") or {}).get("value") or ""
            whatsapp = (presence.get("whatsapp") or {}).get("value") or ""
            max_link = (presence.get("max") or {}).get("value") or ""
            web_lpr = (presence.get("web_lpr") or {}).get("value") or ""
            confirmed_phone = (presence.get("phone") or {}).get("value") or ""
            if confirmed_phone:
                phones = _uniq([confirmed_phone] + phones)
            sites = [site_url] if site_url else []
            if brand_sources and not sites:
                site_source = next(
                    (item for item in brand_sources if item.get("kind") == "site"),
                    None,
                )
                if site_source:
                    site_url = site_source["url"]
                    sites = [site_url]
                    presence["site"] = _found(site_url)
            if brand_sources and not telegram:
                telegram_source = next(
                    (item for item in brand_sources if item.get("kind") == "telegram"),
                    None,
                )
                if telegram_source:
                    telegram = telegram_source["url"]
                    presence["telegram"] = _found(telegram)

        # Object photos only — never mix site/VK gallery into «фото здания»
        object_photos = [
            str(u) for u in (party.get("photos") or []) if u and _image_url_ok(str(u))
        ]
        photos = object_photos[:6]
        if len(photos) < 1:
            checks.append(
                "Фото здания: в открытых источниках не найдено — не подставляем чужие картинки"
            )
            presence["checks"] = checks

        if photos:
            presence["photos"] = {
                "status": "найдено",
                "value": photos[:6],
            }
        else:
            presence["photos"] = {"status": "нет", "value": []}

        routes: list[dict[str, str]] = [
            {"title": "2ГИС", "url": maps_url, "hint": "точка на карте", "status": "открыть"},
            {"title": "Яндекс.Карты", "url": maps_yandex, "hint": "улица/дом объекта", "status": "открыть"},
            {"title": "Google Maps", "url": maps_google, "hint": "сверить фото здания", "status": "открыть"},
        ]
        if inn:
            routes.append(
                {
                    "title": "List-Org",
                    "url": f"https://www.list-org.com/search?type=inn&val={quote_plus(inn)}",
                    "hint": "ЕГРЮЛ / телефоны",
                    "status": "открыть",
                }
            )
            routes.append(
                {
                    "title": "Checko",
                    "url": f"https://checko.ru/search?query={quote_plus(inn)}",
                    "hint": "учредители / численность",
                    "status": "открыть",
                }
            )
            routes.append(
                {
                    "title": "Rusprofile",
                    "url": f"https://www.rusprofile.ru/search?query={quote_plus(inn)}",
                    "hint": "бенефициары / финансы",
                    "status": "открыть",
                }
            )
            routes.append(
                {
                    "title": "ЗаЧестныйБизнес",
                    "url": f"https://zachestnyibiznes.ru/search?query={quote_plus(inn)}",
                    "hint": "сверка выписки",
                    "status": "открыть",
                }
            )
        if site_url:
            routes.append({"title": "Сайт", "url": site_url, "hint": "найдено", "status": "найдено"})
        if vk_company:
            title = (presence.get("vk_group") or {}).get("title") or "группа"
            routes.append(
                {
                    "title": "ВК · группа",
                    "url": vk_company,
                    "hint": title[:40],
                    "status": "найдено",
                }
            )
        else:
            vk_q = " ".join(x for x in (obj_title or short_co, city, "ВК") if x).strip()
            if vk_q:
                routes.append(
                    {
                        "title": "ВК · поиск",
                        "url": (
                            "https://vk.com/search?"
                            + f"c%5Bq%5D={quote_plus(vk_q)}&c%5Bsection%5D=communities"
                        ),
                        "hint": "название + ВК",
                        "status": "открыть",
                    }
                )
        if vk_lpr:
            routes.append({"title": "ВК · ЛПР", "url": vk_lpr, "hint": "найдено", "status": "найдено"})
        if telegram:
            routes.append({"title": "Telegram", "url": telegram, "hint": "найдено", "status": "найдено"})
        for item in brand_sources:
            url = item.get("url") or ""
            if not url or any(route.get("url") == url for route in routes):
                continue
            routes.append(
                {
                    "title": item.get("title") or "Источник сети",
                    "url": url,
                    "hint": item.get("hint") or "открытый источник",
                    "status": "открыть",
                }
            )
        if whatsapp:
            routes.append({"title": "WhatsApp", "url": whatsapp, "hint": "найдено", "status": "найдено"})
        if max_link:
            routes.append({"title": "Max", "url": max_link, "hint": "найдено", "status": "найдено"})
        if web_lpr:
            routes.append({"title": "След ЛПР", "url": web_lpr, "hint": "найдено", "status": "найдено"})
        if list_org_url and not any(r.get("url") == list_org_url for r in routes):
            routes.append(
                {
                    "title": "List-Org",
                    "url": list_org_url,
                    "hint": "карточка юрлица",
                    "status": "открыть",
                }
            )
        checko_url = str(party.get("_checko_url") or "").strip()
        if checko_url and not any(r.get("url") == checko_url for r in routes):
            routes.append(
                {
                    "title": "Checko · учредители",
                    "url": checko_url,
                    "hint": "бенефициары / ССЧ",
                    "status": "открыть",
                }
            )

        online_hits = sum(
            1
            for key in (
                "site",
                "vk_company",
                "vk_lpr",
                "telegram",
                "whatsapp",
                "max",
                "phone",
                "email",
            )
            if (presence.get(key) or {}).get("status") == "найдено"
        )

        party["phones"] = phones[:5]
        party["emails"] = emails[:5]
        party["sites"] = sites[:5]
        party["photos"] = photos[:6]
        party["contact_routes"] = routes
        party["presence"] = presence
        party["online_hits"] = online_hits
        payload = dict(party.get("payload") or {})
        payload.update(
            {
                "phones": phones[:5],
                "emails": emails[:5],
                "sites": sites[:5],
                "photos": photos[:6],
                "contact_routes": routes,
                "presence": presence,
                "online_hits": online_hits,
                "founders": party.get("founders") or [],
                "founders_detail": party.get("founders_detail") or [],
                "employee_count": party.get("employee_count"),
            }
        )
        party["payload"] = payload
        return party
    finally:
        if own:
            await client.aclose()
