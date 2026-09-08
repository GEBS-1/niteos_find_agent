"""Multi-path building owner / UK discovery.

Paths (any can win; results are merged and scored later):
1. DaData party suggest by building title / street / UK phrases
2. Web search (Bing + DuckDuckGo) → extract ИНН from pages/snippets
3. List-Org name search → ИНН from HTML
4. Resolve every ИНН via DaData findById for a full party card

ЕГРН/Росреестр ownership for third parties is restricted — we do not pretend
to have cadastral owner proof without a paid licensed API key.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.contacts import _bing_links, _ddg_links
from app.dadata import DaData
from app.enrich import enrich_from_dadata

log = logging.getLogger(__name__)

_INN_RE = re.compile(r"(?<!\d)(\d{10}|\d{12})(?!\d)")
_INN_URL_RE = re.compile(
    r"(?:inn[=/]|type=inn[^\d]{0,20}|val=|/id/)(\d{10}|\d{12})",
    flags=re.I,
)


def _uniq_inns(items: list[str], limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        inn = re.sub(r"\D", "", str(raw or ""))
        if len(inn) not in (10, 12) or inn in seen:
            continue
        # Skip obvious non-INNs (years, phones stubs)
        if inn.startswith(("0000", "1111", "1234")):
            continue
        seen.add(inn)
        out.append(inn)
        if len(out) >= limit:
            break
    return out


def _extract_inns_from_text(text: str) -> list[str]:
    found: list[str] = []
    for m in _INN_URL_RE.finditer(text or ""):
        found.append(m.group(1))
    for m in _INN_RE.finditer(text or ""):
        # Prefer ИНН near ownership keywords when present
        found.append(m.group(1))
    return _uniq_inns(found, 20)


def _street_hint(address: str) -> str:
    for m in re.finditer(
        r"(?:ул\.?|улица|пр\.?|проспект|пер\.?|переулок)\s*[A-Za-zА-Яа-яЁё0-9\-\s]{3,40}",
        address or "",
        flags=re.I,
    ):
        return m.group(0).strip()
    return ""


def _is_school_title(title: str) -> bool:
    t = (title or "").lower().replace("ё", "е")
    return any(
        w in t
        for w in (
            "школ",
            "лицей",
            "гимнази",
            "мбоу",
            "маоу",
            "сош",
            "колледж",
            "техникум",
            "детский сад",
        )
    )


_FUEL_BRANDS = (
    "татнефть",
    "лукойл",
    "газпромнефть",
    "газпром нефть",
    "роснефть",
    "башнефть",
    "shell",
    "шелл",
    "нефтьмагистраль",
    "ирбис",
    "аспект",
)


def _is_azs_title(title: str) -> bool:
    t = (title or "").lower().replace("ё", "е")
    return any(w in t for w in ("азс", "заправк", "автозаправ")) or any(
        b in t for b in _FUEL_BRANDS
    )


def _azs_brand(title: str) -> str:
    t = (title or "").lower().replace("ё", "е")
    for b in _FUEL_BRANDS:
        if b in t:
            return b
    return ""


def _street_from_title(title: str) -> str:
    """OSM often names POIs as «АЗС (улица …)» — pull street out of parens."""
    m = re.search(r"\(([^)]{4,60})\)", title or "")
    if not m:
        return ""
    inner = m.group(1).strip()
    low = inner.lower().replace("ё", "е")
    if any(
        w in low
        for w in ("ул", "улиц", "пр", "проспект", "пер", "шоссе", "набереж")
    ):
        return inner
    return ""


def _azs_owner_queries(title: str, city: str, street: str) -> list[str]:
    brand = _azs_brand(title)
    street = street or _street_from_title(title)
    q: list[str] = []
    if brand:
        q.extend(
            [
                f"{brand} азс {city}".strip(),
                f"азс {brand} {city}".strip(),
                f"{brand} {city}".strip(),
                f"ооо {brand} {city}".strip(),
            ]
        )
    if street:
        q.extend(
            [
                f"азс {street} {city}".strip(),
                f"автозаправка {street} {city}".strip(),
                f"{street} азс".strip(),
            ]
        )
    q.extend(
        [
            f"{title} {city}".strip(),
            f"азс {city}".strip(),
            title,
        ]
    )
    out: list[str] = []
    seen: set[str] = set()
    for item in q:
        key = item.lower().strip()
        if not key or key in seen or len(key) < 4:
            continue
        seen.add(key)
        out.append(item.strip())
    return out[:12]


def _quoted_building_name(title: str) -> str:
    m = re.search(r"[«\"„]([^»\"“]{3,60})[»\"“]", title or "")
    return (m.group(1) if m else "").strip()


def _is_warehouse_title(title: str) -> bool:
    t = (title or "").lower().replace("ё", "е")
    return any(w in t for w in ("склад", "логист", "терминал", "рц ", " рц"))


def _warehouse_owner_queries(title: str, city: str, street: str) -> list[str]:
    quoted = _quoted_building_name(title)
    q: list[str] = []
    if quoted:
        q.extend(
            [
                f"{quoted} {city}".strip(),
                f"ООО {quoted}",
                f"склад {quoted} {city}".strip(),
                f"{quoted} склад",
                f"УК {quoted}",
            ]
        )
    q.extend(
        [
            f"{title} {city}".strip(),
            title,
            f"склад {city} {street}".strip() if street else f"склад {city}".strip(),
        ]
    )
    if street:
        q.append(f"{street} {city} склад".strip())
    out: list[str] = []
    seen: set[str] = set()
    for item in q:
        key = item.lower().strip()
        if not key or key in seen or len(key) < 4:
            continue
        seen.add(key)
        out.append(item.strip())
    return out[:12]


def _school_number(text: str) -> str:
    m = re.search(
        r"(?:№|n|номер)\s*(\d{1,4})\b|\b(\d{1,4})\s*(?:школ|сош|лицей|гимнази)",
        (text or "").lower().replace("ё", "е"),
        flags=re.I,
    )
    if not m:
        return ""
    return m.group(1) or m.group(2) or ""


def _school_owner_queries(title: str, city: str, street: str) -> list[str]:
    """Schools are usually the legal entity themselves (МБОУ/МАОУ), not a mall UK."""
    num = _school_number(title)
    queries = [
        title,
        f"{title} {city}".strip(),
        f"МБОУ {title} {city}".strip(),
        f"МАОУ {title} {city}".strip(),
        f"{title} {city} образовательное".strip(),
    ]
    if num:
        queries.extend(
            [
                f"МБОУ школа №{num} {city}".strip(),
                f"МАОУ школа №{num} {city}".strip(),
                f"школа №{num} {city}".strip(),
                f"средняя школа №{num} {city}".strip(),
            ]
        )
    if street:
        queries.append(f"{title} {street}".strip())
        if num:
            queries.append(f"школа №{num} {street}".strip())
    return [q for q in queries if q and len(q) >= 3]


async def _path_dadata(
    dadata: DaData,
    *,
    title: str,
    address: str,
    city: str,
    locations: list[dict] | None,
) -> list[dict[str, Any]]:
    street = _street_hint(address) or _street_from_title(title)
    if _is_school_title(title):
        queries = _school_owner_queries(title, city, street)
    elif _is_azs_title(title):
        # Fuel stations are brand/operator entities, not mall UK
        queries = _azs_owner_queries(title, city, street)
    elif _is_warehouse_title(title):
        queries = _warehouse_owner_queries(title, city, street)
    else:
        queries = [
            f"{title} управляющая компания",
            f"УК {title}",
            f"{title} собственник",
            f"{title} {city}".strip(),
            f"ТЦ {title}".strip(),
            f"ТРЦ {title}".strip(),
            title,
        ]
        title_l = title.lower().replace("ё", "е")
        if any(w in title_l for w in ("стадион", "спорт", "арена", "дворец спорта", "бассейн")):
            queries = [
                title,
                f"{title} {city}".strip(),
                f"МУП {title} {city}".strip(),
                f"МБУ {title} {city}".strip(),
                f"дирекция {title} {city}".strip(),
                f"{title} {city} спортивное".strip(),
                f"стадион {city} {street}".strip() if street else f"стадион {city}",
            ] + queries
        if street:
            queries.extend(
                [
                    f"{title} {street}",
                    f"{street} {city}".strip(),
                    f"управляющая компания {street}",
                ]
            )
        if address:
            queries.append(" ".join(address.split(",")[:2]).strip())

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dq in queries:
        if not dq or len(dq) < 3:
            continue
        try:
            batch = await dadata.suggest(dq, count=8, locations=locations)
            if not batch:
                batch = await dadata.suggest(dq, count=8)
        except Exception as exc:
            log.info("owner dadata path failed %s: %s", dq[:40], exc)
            continue
        for item in batch or []:
            data = item.get("data") or {}
            inn = str(data.get("inn") or "")
            if not inn or inn in seen:
                continue
            seen.add(inn)
            out.append(
                {
                    "inn": inn,
                    "source": "dadata",
                    "query": dq,
                    "suggest": item,
                }
            )
    return out


async def _path_web_search(
    http: httpx.AsyncClient, *, title: str, city: str, street: str
) -> list[dict[str, Any]]:
    if _is_school_title(title):
        num = _school_number(title)
        queries = [
            f'"{title}" {city} МБОУ ИНН',
            f'"{title}" {city} ИНН',
            f'"{title}" {city} официальный сайт',
            f"{title} {city} rusprofile",
        ]
        if num:
            queries.insert(0, f'"школа №{num}" {city} МБОУ ИНН')
            queries.append(f'"школа №{num}" {city} ИНН')
        if street:
            queries.append(f'"{title}" {street} ИНН')
    elif _is_azs_title(title):
        brand = _azs_brand(title)
        street = street or _street_from_title(title)
        queries = [
            f'азс {street} {city} ИНН'.strip() if street else f'азс {city} ИНН',
            f'"{title}" {city} ИНН',
            f"{title} {city} rusprofile",
        ]
        if brand:
            queries.insert(0, f'азс {brand} {city} ИНН')
            queries.insert(1, f'{brand} азс {city} ИНН')
    elif _is_warehouse_title(title):
        quoted = _quoted_building_name(title)
        queries = [
            f'"{title}" {city} ИНН',
            f"{title} {city} rusprofile",
            f'"{quoted}" {city} ИНН' if quoted else f'склад {city} ИНН',
        ]
        if quoted:
            queries.insert(0, f'"{quoted}" склад {city} ИНН')
            queries.insert(1, f'ООО "{quoted}" {city}')
    else:
        queries = [
            f'"{title}" {city} управляющая компания ИНН',
            f'"{title}" {city} собственник ИНН',
            f"{title} {city} rusprofile",
        ]
        if street:
            queries.append(f'"{title}" {street} ИНН')

    inns: list[str] = []
    pages_fetched = 0
    from app.websearch import web_search_links

    for q in queries[:4]:
        links: list[str] = []
        try:
            links.extend(await web_search_links(http, q, num=8))
        except Exception:
            pass
        if len(links) < 3:
            try:
                links.extend(await _bing_links(http, q))
            except Exception:
                pass
        if len(links) < 3:
            try:
                links.extend(await _ddg_links(http, q))
            except Exception:
                pass
        for url in links[:8]:
            inns.extend(_extract_inns_from_text(url))
            if pages_fetched >= 3:
                continue
            host = ""
            try:
                from urllib.parse import urlparse

                host = (urlparse(url).netloc or "").lower()
            except Exception:
                continue
            if not any(
                h in host
                for h in ("list-org.", "rusprofile.", "sbis.", "checko.")
            ):
                continue
            try:
                resp = await http.get(url, timeout=8.0)
            except Exception:
                continue
            pages_fetched += 1
            if resp.status_code >= 400 or not resp.text:
                continue
            chunk = resp.text[:80_000]
            inns.extend(_extract_inns_from_text(chunk))
            for m in re.finditer(
                r"ИНН[^0-9]{0,12}(\d{10}|\d{12})", chunk, flags=re.I
            ):
                inns.append(m.group(1))

    out = []
    for inn in _uniq_inns(inns, 8):
        out.append({"inn": inn, "source": "web", "query": title, "suggest": None})
    return out


async def _path_list_org(
    http: httpx.AsyncClient, *, title: str, city: str
) -> list[dict[str, Any]]:
    queries = [f"{title} {city}".strip(), title]
    if _is_school_title(title):
        num = _school_number(title)
        queries = [
            f"МБОУ {title} {city}".strip(),
            f"МАОУ {title} {city}".strip(),
            f"{title} {city}".strip(),
            title,
        ]
        if num:
            queries.insert(0, f"школа №{num} {city}".strip())
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for q in queries:
        if not q or len(q) < 3:
            continue
        try:
            resp = await http.get(
                "https://www.list-org.com/search",
                params={"type": "all", "val": q},
                timeout=15.0,
            )
        except Exception as exc:
            log.info("list-org search failed: %s", exc)
            continue
        if resp.status_code >= 400 or not resp.text:
            continue
        html = resp.text[:200_000]
        for m in re.finditer(
            r"href=['\"]/company/(\d+)['\"]([\s\S]{0,500})", html, flags=re.I
        ):
            ctx = m.group(0)
            for inn in _extract_inns_from_text(ctx):
                if inn in seen:
                    continue
                ctx_l = ctx.lower().replace("ё", "е")
                title_l = title.lower().replace("ё", "е")
                token_hit = any(
                    t in ctx_l
                    for t in re.findall(r"[а-яa-z0-9]{4,}", title_l)[:4]
                )
                city_hit = (city or "").lower().replace("ё", "е") in ctx_l
                if not (token_hit or city_hit or not city):
                    continue
                seen.add(inn)
                out.append(
                    {
                        "inn": inn,
                        "source": "list-org",
                        "query": q,
                        "suggest": None,
                        "list_org_id": m.group(1),
                    }
                )
        # Fallback: any INN on the search page labeled as ИНН
        for m in re.finditer(r"ИНН[^0-9]{0,12}(\d{10}|\d{12})", html, flags=re.I):
            inn = m.group(1)
            if inn not in seen:
                seen.add(inn)
                out.append(
                    {"inn": inn, "source": "list-org", "query": q, "suggest": None}
                )
        if out:
            break
    return out[:10]


async def _hydrate_inns(
    dadata: DaData, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach DaData suggest payloads for INN-only hits."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cand in candidates:
        inn = str(cand.get("inn") or "")
        if not inn or inn in seen:
            continue
        seen.add(inn)
        suggest = cand.get("suggest")
        if not suggest:
            try:
                suggest = await dadata.find_by_inn(inn)
            except Exception as exc:
                log.info("hydrate inn %s failed: %s", inn, exc)
                suggest = None
        if not suggest:
            continue
        out.append({**cand, "suggest": suggest, "inn": inn})
    return out


def _uk_rank(item: dict[str, Any], building_title: str) -> int:
    data = item.get("data") or {}
    name = str(item.get("value") or data.get("name") or "").lower().replace("ё", "е")
    okved = ""
    if isinstance(data.get("okved"), str):
        okved = data["okved"]
    elif isinstance(data.get("okveds"), list) and data["okveds"]:
        first = data["okveds"][0]
        okved = str((first or {}).get("code") or first or "")
    score = 0
    school = _is_school_title(building_title)
    if school:
        if any(
            w in name
            for w in ("школ", "лицей", "гимнази", "мбоу", "маоу", "сош", "образован")
        ):
            score += 50
        if okved.startswith("85"):
            score += 30
        sn_b = _school_number(building_title)
        sn_n = _school_number(name)
        if sn_b and sn_n and sn_b == sn_n:
            score += 40
        if any(w in name for w in ("торгов", "мега", "ритейл", "гипермаркет")):
            score -= 50
    else:
        if any(w in name for w in ("управл", "ук ", "ук«", "собствен", "девелоп")):
            score += 40
        if okved.startswith(("68.32", "68.20", "68.3", "41.20")):
            score += 25
        if any(w in (building_title or "").lower() for w in ("стадион", "спорт", "арена", "бассейн")):
            if any(
                w in name
                for w in ("стадион", "спорт", "арена", "муп", "мбу", "дирекция", "физкультур")
            ):
                score += 45
            if okved.startswith(("93", "85.41", "84.")) or "93." in okved:
                score += 25
        if _is_azs_title(building_title):
            if any(
                w in name
                for w in ("азс", "нефть", "топлив", "заправ", "бензин", *_FUEL_BRANDS)
            ):
                score += 50
            if okved.startswith(("47.30", "46.71", "19.2", "47.3")):
                score += 35
            brand = _azs_brand(building_title)
            if brand and brand in name:
                score += 25
        if _is_warehouse_title(building_title):
            quoted = _quoted_building_name(building_title).lower().replace("ё", "е")
            if quoted and quoted in name:
                score += 55
            if any(w in name for w in ("склад", "логист", "терминал", "управл", "девелоп")):
                score += 35
            if okved.startswith(("52.", "68.", "41.")):
                score += 20
    if any(w in name for w in ("магазин", "ресторан", "гостиниц", "отел", "аптек")):
        if not _is_azs_title(building_title):
            score -= 40
    ot = {t for t in re.findall(r"[а-яa-z0-9]{3,}", (building_title or "").lower())}
    nt = {t for t in re.findall(r"[а-яa-z0-9]{3,}", name)}
    score += min(30, len(ot & nt) * 10)
    return score


async def _path_llm(
    http: httpx.AsyncClient,
    dadata: DaData,
    llm: Any,
    *,
    title: str,
    address: str,
    city: str,
    street: str,
) -> list[dict[str, Any]]:
    """Ask LLM which company owns/operates the building, then resolve via DaData."""
    if llm is None or not getattr(llm, "available", False):
        return []
    snippets: list[str] = []
    if _is_school_title(title):
        num = _school_number(title)
        queries = [
            f'"{title}" {city} МБОУ',
            f'"{title}" {city} официальный сайт',
            f'"{title}" {city} ИНН',
        ]
        if num:
            queries.insert(0, f'"школа №{num}" {city} МБОУ')
        if street:
            queries.append(f'"{title}" {street}')
        task_hint = (
            "Это школа/соцучреждение. Найди юрлицо (МБОУ/МАОУ/школа №…), "
            "не УК торгового центра. Не выдумывай ИНН."
        )
        system_hint = (
            "Ты исследователь B2B по школам и соцучреждениям в России. "
            "Ответь строго JSON: "
            '{"companies":[{"name":"...","role":"owner|operator|uk|unknown",'
            '"inn":"","why":"..."}],"search_names":["..."]}. '
            "Максимум 5 companies и 5 search_names. "
            "Если данных мало — пустые списки, не фантазируй."
        )
    else:
        queries = [
            f'"{title}" {city} кому принадлежит',
            f'"{title}" {city} управляющая компания',
            f'"{title}" {city} собственник',
        ]
        if street:
            queries.append(f'"{title}" {street} УК')
        task_hint = (
            "По открытым следам определи, какая компания скорее владеет или "
            "управляет этим зданием (УК/оператор/собственник-юрлицо). "
            "Не выдумывай ИНН. Верни JSON."
        )
        system_hint = (
            "Ты исследователь B2B по коммерческой недвижимости в России. "
            "Ответь строго JSON: "
            '{"companies":[{"name":"...","role":"owner|operator|uk|unknown",'
            '"inn":"","why":"..."}],"search_names":["..."]}. '
            "Максимум 5 companies и 5 search_names. "
            "Если данных мало — пустые списки, не фантазируй."
        )
    # Prefer RouterAI web plugin (same key). Skip Brave/Bing scrapes — they hang/429.
    use_web = True
    snippets = [
        f"Здание: {title}",
        f"Адрес: {address}",
        f"Город: {city}",
        f"Поисковые запросы: {'; '.join(queries[:4])}",
    ]
    user = {
        "building": title,
        "address": address,
        "city": city,
        "evidence": snippets[:18],
        "task": task_hint,
    }
    try:
        data = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": system_hint,
                },
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=700,
            web=use_web,
            web_max_results=8,
        )
    except TypeError:
        # Older RouterAI client without web= kwargs
        try:
            data = await llm.chat_json(
                [
                    {"role": "system", "content": system_hint},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                temperature=0.0,
                max_tokens=700,
            )
        except Exception as exc:
            log.info("llm owner path failed: %s", exc)
            return []
    except Exception as exc:
        log.info("llm owner path failed: %s", exc)
        return []
    if not isinstance(data, dict):
        return []
    names: list[str] = []
    inns: list[str] = []
    for row in (data.get("companies") or [])[:5]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        inn = re.sub(r"\D", "", str(row.get("inn") or ""))
        if name:
            names.append(name)
        if len(inn) in (10, 12):
            inns.append(inn)
    for name in (data.get("search_names") or [])[:5]:
        text = str(name or "").strip()
        if text:
            names.append(text)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for inn in _uniq_inns(inns, 5):
        out.append({"inn": inn, "source": "llm", "query": title, "suggest": None})
        seen.add(inn)
    for name in names:
        try:
            batch = await dadata.suggest(f"{name} {city}".strip(), count=5)
            if not batch:
                batch = await dadata.suggest(name, count=5)
        except Exception:
            continue
        for item in batch or []:
            data_item = item.get("data") or {}
            inn = str(data_item.get("inn") or "")
            if not inn or inn in seen:
                continue
            seen.add(inn)
            out.append(
                {
                    "inn": inn,
                    "source": "llm",
                    "query": name,
                    "suggest": item,
                }
            )
    return out


async def resolve_building_owners(
    *,
    http: httpx.AsyncClient,
    dadata: DaData,
    obj: dict[str, Any],
    locations: list[dict] | None = None,
    city: str = "",
    llm: Any | None = None,
) -> list[dict[str, Any]]:
    """Return ranked hydrated DaData suggestions with source tags."""
    title = str(obj.get("title") or "").strip()
    address = str(obj.get("address") or "").strip()
    city = (city or str(obj.get("city") or "")).strip()
    if not title:
        return []

    street = _street_hint(address)
    merged: list[dict[str, Any]] = []
    try:
        merged.extend(
            await _path_dadata(
                dadata,
                title=title,
                address=address,
                city=city,
                locations=locations,
            )
        )
    except Exception as exc:
        log.exception("dadata owner path: %s", exc)

    try:
        merged.extend(await _path_list_org(http, title=title, city=city))
    except Exception as exc:
        log.exception("list-org owner path: %s", exc)

    # Free web owner search when DaData is thin.
    # IMPORTANT: do NOT skip this just because RouterAI key exists —
    # expensive LLM owner path is off by default (HUNT_LLM_OWNER=0).
    from app.cost_guard import llm_owner_enabled

    need_web = len(merged) < 2
    use_llm_owner = (
        llm_owner_enabled()
        and llm is not None
        and getattr(llm, "available", False)
    )
    if need_web and not use_llm_owner:
        try:
            merged.extend(
                await asyncio.wait_for(
                    _path_web_search(http, title=title, city=city, street=street),
                    timeout=22.0,
                )
            )
        except Exception as exc:
            log.info("web owner path skipped/failed: %s", exc)

    if use_llm_owner and len(merged) < 4:
        try:
            merged.extend(
                await asyncio.wait_for(
                    _path_llm(
                        http,
                        dadata,
                        llm,
                        title=title,
                        address=address,
                        city=city,
                        street=street,
                    ),
                    timeout=45.0,
                )
            )
        except Exception as exc:
            log.info("llm owner path skipped/failed: %s", exc)

    hydrated = await _hydrate_inns(dadata, merged)
    hydrated.sort(
        key=lambda c: (
            _uk_rank(c.get("suggest") or {}, title),
            1 if c.get("source") in {"llm", "dadata"} else 0,
        ),
        reverse=True,
    )
    return hydrated


def candidate_party(cand: dict[str, Any]) -> dict[str, Any] | None:
    suggest = cand.get("suggest")
    if not suggest:
        return None
    return enrich_from_dadata(suggest)


def candidate_sources_summary(cands: list[dict[str, Any]]) -> str:
    sources = sorted({str(c.get("source") or "") for c in cands if c.get("source")})
    inns = [str(c.get("inn") or "") for c in cands[:5] if c.get("inn")]
    parts = []
    if sources:
        parts.append("пути: " + ", ".join(sources))
    if inns:
        parts.append("инн-кандидаты: " + ", ".join(inns))
    return "; ".join(parts)
