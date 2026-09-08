"""Cheap, evidence-first building -> legal entity resolver.

The mass hunt must not depend on an LLM.  This module gathers candidates from
DaData, List-Org and free web search, hydrates them through DaData and ranks
them with deterministic evidence.  RouterAI is an optional last resort only
when HUNT_CHEAP_MODE=0 and HUNT_LLM_OWNER=1.

Public data can prove that a company is plausibly connected to an object, but
it must not be presented as cadastral ownership proof unless such proof comes
from an authorised property source.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.contacts import _bing_links, _ddg_links
from app.cost_guard import llm_owner_enabled
from app.dadata import DaData
from app.enrich import enrich_from_dadata

log = logging.getLogger(__name__)

_INN_RE = re.compile(r"(?<!\d)(\d{10}|\d{12})(?!\d)")
_INN_URL_RE = re.compile(
    r"(?:inn[=/]|type=inn[^\d]{0,20}|val=|/id/)(\d{10}|\d{12})", re.I
)
_WORD_RE = re.compile(r"[a-zа-яё0-9]{3,}", re.I)

_FUEL_BRANDS = (
    "татнефть",
    "лукойл",
    "газпромнефть",
    "газпром нефть",
    "роснефть",
    "башнефть",
    "нефтьмагистраль",
    "ирбис",
    "shell",
    "шелл",
)

_STOP_WORDS = {
    "ооо",
    "ао",
    "пао",
    "зао",
    "оао",
    "ип",
    "торговый",
    "центр",
    "бизнес",
    "компания",
    "общество",
    "здание",
    "объект",
    "город",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е")).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(_norm(text)) if t not in _STOP_WORDS}


def _uniq_inns(items: list[str], limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        inn = re.sub(r"\D", "", str(raw or ""))
        if len(inn) not in (10, 12) or inn in seen:
            continue
        if inn.startswith(("0000", "1111", "1234")):
            continue
        seen.add(inn)
        out.append(inn)
        if len(out) >= limit:
            break
    return out


def _extract_inns_from_text(text: str) -> list[str]:
    values = [m.group(1) for m in _INN_URL_RE.finditer(text or "")]
    values.extend(m.group(1) for m in _INN_RE.finditer(text or ""))
    return _uniq_inns(values, 20)


def _street_hint(address: str) -> str:
    m = re.search(
        r"(?:ул\.?|улица|пр\.?|проспект|пер\.?|переулок|шоссе|наб\.?|набережная)"
        r"\s*[A-Za-zА-Яа-яЁё0-9\-\s]{3,50}",
        address or "",
        re.I,
    )
    return m.group(0).strip() if m else ""


def _house_hint(address: str) -> str:
    m = re.search(r"(?:д\.?|дом)\s*(\d+[а-яa-z]?(?:/\d+)?)", _norm(address), re.I)
    return (m.group(1) if m else "").strip()


def _school_number(text: str) -> str:
    m = re.search(
        r"(?:№|n|номер)\s*(\d{1,4})\b|\b(\d{1,4})\s*(?:школ|сош|лицей|гимнази)",
        _norm(text),
        re.I,
    )
    return (m.group(1) or m.group(2) or "") if m else ""


def _is_school(title: str) -> bool:
    t = _norm(title)
    return any(x in t for x in ("школ", "лицей", "гимнази", "мбоу", "маоу", "сош", "детский сад"))


def _is_warehouse(title: str) -> bool:
    t = _norm(title)
    return any(x in t for x in ("склад", "логист", "терминал", "распределительный центр", " рц"))


def _is_azs(title: str) -> bool:
    t = _norm(title)
    return any(x in t for x in ("азс", "заправ", "автозаправ")) or any(b in t for b in _FUEL_BRANDS)


def _is_sport(title: str) -> bool:
    t = _norm(title)
    return any(x in t for x in ("стадион", "арена", "спорт", "бассейн", "дворец спорта"))


def _quoted_name(title: str) -> str:
    m = re.search(r"[«\"„]([^»\"“]{3,60})[»\"“]", title or "")
    return (m.group(1) if m else "").strip()


def _brand(title: str) -> str:
    t = _norm(title)
    for brand in _FUEL_BRANDS:
        if brand in t:
            return brand
    return ""


def _owner_queries(title: str, address: str, city: str) -> list[str]:
    street = _street_hint(address)
    quoted = _quoted_name(title)
    queries: list[str] = []

    if _is_school(title):
        number = _school_number(title)
        queries.extend((title, f"{title} {city}".strip(), f"МБОУ {title} {city}".strip(), f"МАОУ {title} {city}".strip()))
        if number:
            queries.extend((f"школа №{number} {city}".strip(), f"МБОУ школа №{number} {city}".strip()))
    elif _is_azs(title):
        brand = _brand(title)
        if brand:
            queries.extend((f"{brand} АЗС {city}".strip(), f"ООО {brand} {city}".strip(), f"{brand} {city}".strip()))
        queries.extend((f"{title} {city}".strip(), title))
    elif _is_warehouse(title):
        if quoted:
            queries.extend((f"{quoted} {city}".strip(), f"ООО {quoted}", f"склад {quoted} {city}".strip()))
        queries.extend((f"{title} {city}".strip(), title))
    else:
        queries.extend(
            (
                f"{title} {city}".strip(),
                f"{title} управляющая компания",
                f"УК {title}",
                f"{title} собственник",
                title,
            )
        )
        if _is_sport(title):
            queries.extend((f"МБУ {title} {city}".strip(), f"МУП {title} {city}".strip(), f"дирекция {title} {city}".strip()))

    if street:
        queries.extend((f"{title} {street}", f"{street} {city}".strip()))
    if address:
        queries.append(" ".join(x.strip() for x in address.split(",")[:3] if x.strip()))

    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        q = re.sub(r"\s+", " ", q).strip()
        key = _norm(q)
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out[:12]


async def _path_dadata(
    dadata: DaData,
    *,
    title: str,
    address: str,
    city: str,
    locations: list[dict] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in _owner_queries(title, address, city):
        try:
            batch = await dadata.suggest(query, count=8, locations=locations)
            if not batch:
                batch = await dadata.suggest(query, count=8)
        except Exception as exc:
            log.info("owner dadata failed for %s: %s", query[:60], exc)
            continue
        for suggest in batch or []:
            data = suggest.get("data") or {}
            inn = str(data.get("inn") or "")
            if not inn or inn in seen:
                continue
            seen.add(inn)
            out.append({"inn": inn, "source": "dadata", "query": query, "suggest": suggest})
        if len(out) >= 18:
            break
    return out


async def _path_list_org(http: httpx.AsyncClient, *, title: str, city: str) -> list[dict[str, Any]]:
    queries = [f"{title} {city}".strip(), title]
    if _is_school(title) and _school_number(title):
        queries.insert(0, f"школа №{_school_number(title)} {city}".strip())
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        try:
            resp = await http.get(
                "https://www.list-org.com/search",
                params={"type": "all", "val": query},
                timeout=12.0,
            )
        except Exception:
            continue
        if resp.status_code >= 400 or not resp.text:
            continue
        html = resp.text[:220_000]
        for inn in _extract_inns_from_text(html):
            if inn in seen:
                continue
            seen.add(inn)
            out.append({"inn": inn, "source": "list-org", "query": query, "suggest": None})
            if len(out) >= 8:
                return out
        if out:
            break
    return out


async def _path_web(http: httpx.AsyncClient, *, title: str, address: str, city: str) -> list[dict[str, Any]]:
    street = _street_hint(address)
    queries = [
        f'"{title}" {city} ИНН',
        f'"{title}" {city} управляющая компания ИНН',
        f'"{title}" {city} собственник ИНН',
    ]
    if _is_school(title):
        queries = [f'"{title}" {city} МБОУ ИНН', f'"{title}" {city} ИНН'] + queries[:1]
    elif _is_azs(title) and _brand(title):
        queries.insert(0, f'{_brand(title)} АЗС {city} ИНН')
    elif _is_warehouse(title):
        queries.insert(0, f'"{title}" {city} склад ИНН')
    if street:
        queries.append(f'"{title}" "{street}" ИНН')

    inns: list[str] = []
    fetched_pages = 0
    try:
        from app.websearch import web_search_links
    except Exception:
        web_search_links = None

    for query in queries[:4]:
        links: list[str] = []
        if web_search_links is not None:
            try:
                links.extend(await web_search_links(http, query, num=6))
            except Exception:
                pass
        if len(links) < 3:
            try:
                links.extend(await _bing_links(http, query))
            except Exception:
                pass
        if len(links) < 3:
            try:
                links.extend(await _ddg_links(http, query))
            except Exception:
                pass

        for url in links[:7]:
            inns.extend(_extract_inns_from_text(url))
            if fetched_pages >= 3:
                continue
            host = ""
            try:
                from urllib.parse import urlparse
                host = (urlparse(url).netloc or "").lower()
            except Exception:
                pass
            if not any(x in host for x in ("list-org.", "rusprofile.", "checko.", "sbis.")):
                continue
            try:
                resp = await http.get(url, timeout=8.0)
            except Exception:
                continue
            fetched_pages += 1
            if resp.status_code < 400 and resp.text:
                inns.extend(_extract_inns_from_text(resp.text[:100_000]))

    return [{"inn": inn, "source": "web", "query": title, "suggest": None} for inn in _uniq_inns(inns, 8)]


async def _hydrate(dadata: DaData, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        inn = str(row.get("inn") or "")
        if not inn or inn in seen:
            continue
        seen.add(inn)
        suggest = row.get("suggest")
        if not suggest:
            try:
                suggest = await dadata.find_by_inn(inn)
            except Exception:
                suggest = None
        if suggest:
            out.append({**row, "suggest": suggest})
    return out


def _candidate_score(cand: dict[str, Any], *, title: str, address: str, city: str) -> tuple[int, list[str]]:
    suggest = cand.get("suggest") or {}
    data = suggest.get("data") or {}
    name = str(suggest.get("value") or data.get("name") or "")
    legal_address = str(data.get("address", {}).get("value") if isinstance(data.get("address"), dict) else data.get("address") or "")
    okved = str(data.get("okved") or "")
    n = _norm(name)
    score = 0
    reasons: list[str] = []

    source = str(cand.get("source") or "")
    if source == "dadata":
        score += 12
        reasons.append("кандидат найден через DaData по объектному запросу")
    elif source == "list-org":
        score += 10
        reasons.append("кандидат найден через List-Org")
    elif source == "web":
        score += 8
        reasons.append("ИНН найден в веб-следах объекта")
    elif source == "llm":
        score += 4

    overlap = _tokens(title) & _tokens(name)
    if overlap:
        add = min(34, 12 * len(overlap))
        score += add
        reasons.append("совпало название: " + ", ".join(sorted(overlap)[:3]))

    quoted = _norm(_quoted_name(title))
    if quoted and len(quoted) >= 4 and quoted in n:
        score += 30
        reasons.append("имя объекта присутствует в названии юрлица")

    if city and _norm(city) in _norm(legal_address):
        score += 8
        reasons.append("совпадает город")

    street = _street_hint(address)
    house = _house_hint(address)
    if street and _tokens(street) & _tokens(legal_address):
        score += 18
        reasons.append("совпадает улица")
    if house and re.search(rf"(?:д\.?|дом)?\s*{re.escape(house)}\b", _norm(legal_address)):
        score += 14
        reasons.append("совпадает номер дома")

    if _is_school(title):
        number = _school_number(title)
        if any(x in n for x in ("школ", "лицей", "гимнази", "мбоу", "маоу", "сош")):
            score += 35
            reasons.append("юрлицо образовательного учреждения")
        if number and _school_number(name) == number:
            score += 35
            reasons.append(f"совпадает номер школы №{number}")
        if okved.startswith("85"):
            score += 18
            reasons.append("ОКВЭД образования")
    elif _is_azs(title):
        brand = _brand(title)
        if brand and brand in n:
            score += 36
            reasons.append("совпадает бренд АЗС")
        if any(x in n for x in ("нефть", "топлив", "азс", "заправ")):
            score += 20
            reasons.append("юрлицо топливного профиля")
        if okved.startswith(("47.30", "46.71", "19.2")):
            score += 18
            reasons.append("профильный ОКВЭД АЗС")
    elif _is_warehouse(title):
        if any(x in n for x in ("склад", "логист", "терминал", "девелоп", "управл", "недвиж")):
            score += 24
            reasons.append("юрлицо складского/недвижимого профиля")
        if okved.startswith(("52.", "68.", "41.")):
            score += 14
            reasons.append("профильный ОКВЭД")
    elif _is_sport(title):
        if any(x in n for x in ("стадион", "спорт", "арена", "мбу", "муп", "дирекция", "физкультур")):
            score += 30
            reasons.append("похоже на оператора спортобъекта")
    else:
        if any(x in n for x in ("управл", "девелоп", "недвиж", "собствен")):
            score += 24
            reasons.append("похоже на УК/девелопера")
        if okved.startswith(("68.32", "68.20", "68.3", "41.20")):
            score += 14
            reasons.append("ОКВЭД управления/недвижимости")

    if not _is_azs(title) and any(x in n for x in ("ресторан", "аптек", "гостиниц", "отел", "магазин", "банк")):
        score -= 30
        reasons.append("похоже на арендатора")

    return max(0, min(score, 100)), reasons


async def _path_llm(
    dadata: DaData,
    llm: Any,
    *,
    title: str,
    address: str,
    city: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Optional no-web resolver over already collected evidence."""
    if llm is None or not getattr(llm, "available", False) or not llm_owner_enabled():
        return []
    evidence = []
    for cand in candidates[:6]:
        party = enrich_from_dadata(cand.get("suggest") or {})
        evidence.append(
            {
                "inn": cand.get("inn"),
                "name": party.get("name"),
                "address": party.get("address"),
                "okved": party.get("okved"),
                "source": cand.get("source"),
                "resolver_score": cand.get("resolver_score"),
            }
        )
    if not evidence:
        return []
    prompt = {
        "building": {"title": title, "address": address, "city": city},
        "candidates": evidence,
        "task": "Choose only the most plausible operator/owner/management company. Never invent an INN.",
    }
    try:
        data = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты проверяешь уже найденные факты по объекту недвижимости. "
                        "Не ищи в интернете. Ответ строго JSON: "
                        '{"inn":"","role":"owner|operator|uk|unknown","confidence":0,"why":""}. '
                        "Если доказательств мало, верни пустой inn."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=220,
            web=False,
        )
    except Exception as exc:
        log.info("cheap llm owner judge failed: %s", exc)
        return []
    inn = re.sub(r"\D", "", str((data or {}).get("inn") or ""))
    if len(inn) not in (10, 12):
        return []
    for cand in candidates:
        if str(cand.get("inn") or "") == inn:
            cand = dict(cand)
            cand["source"] = "llm-judge"
            cand["llm_role"] = str(data.get("role") or "unknown")
            cand["llm_confidence"] = int(data.get("confidence") or 0)
            cand["llm_why"] = str(data.get("why") or "")[:300]
            return [cand]
    try:
        suggest = await dadata.find_by_inn(inn)
    except Exception:
        suggest = None
    return [{"inn": inn, "source": "llm-judge", "query": title, "suggest": suggest}] if suggest else []


async def resolve_building_owners(
    *,
    http: httpx.AsyncClient,
    dadata: DaData,
    obj: dict[str, Any],
    locations: list[dict] | None = None,
    city: str = "",
    llm: Any | None = None,
) -> list[dict[str, Any]]:
    """Return ranked candidates; mass mode is deterministic and LLM-free."""
    title = str(obj.get("title") or "").strip()
    address = str(obj.get("address") or "").strip()
    city = (city or str(obj.get("city") or "")).strip()
    if not title:
        return []

    merged: list[dict[str, Any]] = []
    try:
        merged.extend(await _path_dadata(dadata, title=title, address=address, city=city, locations=locations))
    except Exception as exc:
        log.info("dadata owner path failed: %s", exc)
    try:
        merged.extend(await _path_list_org(http, title=title, city=city))
    except Exception as exc:
        log.info("list-org owner path failed: %s", exc)

    # Free web is a fallback, not an unconditional step for every building.
    if len({str(x.get('inn') or '') for x in merged if x.get('inn')}) < 2:
        try:
            merged.extend(
                await asyncio.wait_for(
                    _path_web(http, title=title, address=address, city=city), timeout=22.0
                )
            )
        except Exception as exc:
            log.info("free web owner fallback failed: %s", exc)

    hydrated = await _hydrate(dadata, merged)
    ranked: list[dict[str, Any]] = []
    for cand in hydrated:
        score, reasons = _candidate_score(cand, title=title, address=address, city=city)
        ranked.append({**cand, "resolver_score": score, "resolver_reasons": reasons})
    ranked.sort(key=lambda x: (int(x.get("resolver_score") or 0), 1 if x.get("source") == "dadata" else 0), reverse=True)

    # Optional deep mode: judge already-collected candidates, no RouterAI web plugin.
    if llm_owner_enabled() and ranked and int(ranked[0].get("resolver_score") or 0) < 82:
        judged = await _path_llm(dadata, llm, title=title, address=address, city=city, candidates=ranked)
        if judged:
            chosen_inn = str(judged[0].get("inn") or "")
            ranked.sort(key=lambda x: (1 if str(x.get("inn") or "") == chosen_inn else 0, int(x.get("resolver_score") or 0)), reverse=True)
            ranked[0].update({k: v for k, v in judged[0].items() if k.startswith("llm_") or k == "source"})

    return ranked[:12]


def candidate_party(cand: dict[str, Any]) -> dict[str, Any] | None:
    suggest = cand.get("suggest")
    if not suggest:
        return None
    party = enrich_from_dadata(suggest)
    party["resolver_score"] = int(cand.get("resolver_score") or 0)
    party["resolver_reasons"] = list(cand.get("resolver_reasons") or [])
    party["owner_source"] = str(cand.get("source") or "")
    if cand.get("llm_role"):
        party["resolver_role"] = cand.get("llm_role")
    return party


def candidate_sources_summary(cands: list[dict[str, Any]]) -> str:
    if not cands:
        return "кандидатов нет"
    sources = sorted({str(c.get("source") or "") for c in cands if c.get("source")})
    top = cands[:3]
    bits = [
        f"{c.get('inn') or '?'}:{int(c.get('resolver_score') or 0)}"
        for c in top
    ]
    return f"пути: {', '.join(sources) or 'нет'}; топ: {', '.join(bits)}"
