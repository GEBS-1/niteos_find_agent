from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.config import Settings
from app import db
from app.cost_guard import cheap_mode_enabled, llm_oneshot_enabled
from app.dadata import DaData
from app.card_audit import run_final_card_audit
from app.contacts import enrich_contacts
from app.enrich import FnsBfo, enrich_from_dadata, format_money_rub, merge_fns_finance
from app.llm import RouterAI
from app.llm_oneshot import build_cards_oneshot
from app.geo_tree import address_matches_geo, dadata_locations_multi, parse_geo_selection
from app.objects import (
    MIN_PHOTO_RELATION_CONFIDENCE,
    MIN_RELATION_CONFIDENCE,
    accept_building_candidate,
    building_dedupe_key,
    collect_object_photos,
    is_building_grade_title,
    is_generic_object_title,
    is_school_building_title,
    is_sports_building_title,
    is_tenant_inside_host,
    object_company_relation,
    object_photo_ok,
    recommend_object,
    relation_accepted,
    relation_usable,
    search_objects,
    short_company_label,
    streetish_address,
)
from app.owners import (
    candidate_party,
    candidate_sources_summary,
    resolve_building_owners,
)
from app.okved import title_for
from app.qualification import qualify_lead
from app.match import expand_phrase_queries, is_brand_query, matches_search_intent
from app.spheres import SPHERES, parse_okved

log = logging.getLogger(__name__)

Progress = Callable[[str], Awaitable[None]]

_COMPANY_ADDRESS_FALLBACK_SPHERES = {
    "commercial",
    "office",
    "warehouse",
    "industry",
    "azs",
    "housing",
    "social",
    "sports",
}


def _score(
    sphere_id: str,
    status: str,
    has_management: bool,
    online_hits: int = 0,
    has_finance: bool = False,
    object_confirmed: bool = False,
    non_object_legal_entity: bool = False,
) -> tuple[int, str, str]:
    if status and status != "ACTIVE":
        return 0, "стоп", "Компания не действующая — в работу не берём"
    if non_object_legal_entity:
        return (
            25,
            "не объект",
            "Это похоже на публичное/управляющее юрлицо без подтверждённого объекта — искать конкретное здание",
        )
    base = {
        "warehouse": 72,
        "azs": 76,
        "industry": 74,
        "shops": 58,
        "laundry": 60,
        "commercial": 70,
        "sports": 68,
        "street": 66,
        "housing": 62,
        "social": 60,
        "office": 64,
    }.get(sphere_id, 55)
    if has_management:
        base += 6
    if has_finance:
        base += 4
    base += min(max(online_hits, 0), 4) * 3
    if object_confirmed:
        base += 10
    else:
        base -= 18
    base = min(base, 99)
    if base >= 70:
        stamp = "в работу"
        hint = "Приоритет высокий: объект подходит; личный контакт ЛПР нужно подтвердить"
    elif base >= 55:
        stamp = "осторожно"
        hint = "Средний приоритет: проверить контакты и объект"
    else:
        stamp = "слабо"
        hint = "Мало сигналов — лучше сменить запрос или географию"
    return base, stamp, hint


def stamp_label(stamp: str, score: int) -> str:
    return f"{stamp} · приоритет {score}/99"


def lighting_score(card: dict[str, Any]) -> dict[str, Any]:
    """V5 sales-card signal: whether this object is worth lighting work."""
    obj = card.get("object") or {}
    photos = [str(u) for u in (card.get("photos") or []) if str(u).strip()]
    map_url = str(obj.get("maps_yandex") or "")
    title = str(obj.get("title") or card.get("name") or "").lower().replace("ё", "е")
    notes = " ".join(str(x) for x in (obj.get("photo_notes") or [])).lower()

    score = 0
    reasons: list[str] = []
    if photos:
        score += 30
        reasons.append("есть фото фасада")
    if map_url:
        score += 20
        reasons.append("есть ссылка на карты/панораму")
    if any(x in notes for x in ("снаружи", "фасад", "обложка яндекс")):
        score += 15
        reasons.append("фото похоже на внешний вид здания")
    if any(
        x in title
        for x in (
            "бизнес",
            "бц",
            "тц",
            "трц",
            "гостиниц",
            "отел",
            "завод",
            "арена",
            "стадион",
            "жк",
            "склад",
        )
    ):
        score += 20
        reasons.append("тип здания подходит под архитектурную подсветку")
    if obj.get("address") or card.get("object_address"):
        score += 10
        reasons.append("есть адрес для выезда/проверки")

    score = min(score, 100)
    return {
        "score": score,
        "status": "high" if score >= 75 else "medium" if score >= 50 else "low",
        "reasons": reasons,
    }


def _filter_object_photos(flat: dict[str, Any]) -> None:
    from app.objects import _normalize_yandex_altay_url

    photos: list[str] = []
    for u in flat.get("photos") or []:
        if not u:
            continue
        raw = str(u)
        img = (
            _normalize_yandex_altay_url(raw)
            if "get-altay" in raw.lower()
            else raw
        )
        if object_photo_ok(img):
            photos.append(img)
    flat["photos"] = photos[:6]
    presence = flat.get("presence") or {}
    item = presence.get("photos") or {}
    value = item.get("value") if isinstance(item, dict) else []
    if isinstance(value, list):
        presence_photos = []
        for u in value:
            if not u:
                continue
            raw = str(u)
            img = (
                _normalize_yandex_altay_url(raw)
                if "get-altay" in raw.lower()
                else raw
            )
            if object_photo_ok(img):
                presence_photos.append(img)
        if presence_photos:
            presence["photos"] = {
                **item,
                "status": "найдено",
                "value": presence_photos[:6],
            }
        else:
            presence["photos"] = {"status": "нет", "value": []}
        flat["presence"] = presence
    # Keep photo_notes honest vs filtered list
    obj = flat.get("object")
    if isinstance(obj, dict):
        notes = [
            n
            for n in (obj.get("photo_notes") or [])
            if not re.search(r"фото\s*(объекта|с открытых)?[^:]*:\s*\d+", str(n), re.I)
        ]
        if flat["photos"]:
            notes.append(f"фото объекта: {len(flat['photos'])}")
        else:
            if not any("не найден" in str(n).lower() for n in notes):
                notes.append("фото объекта в открытых источниках не найдено")
        obj["photo_notes"] = notes
        flat["object"] = obj


def _idea(sphere_ids: list[str], phrase: str) -> str:
    for sid in sphere_ids:
        if sid in SPHERES:
            return SPHERES[sid].idea
    if phrase.strip():
        return f"По запросу «{phrase.strip()}»: подобрать линейку Нитеос под объект"
    return "Нужна линейка под тип объекта"


def _object_card_id(title: str, address: str) -> str:
    raw = re.sub(r"\s+", " ", f"{title}|{address}".lower().replace("ё", "е")).strip()
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"OBJ-{digest}"


def _okved_prefixes(sphere_ids: list[str], extra: list[str]) -> list[str]:
    codes = list(extra)
    for sid in sphere_ids:
        sphere = SPHERES.get(sid)
        if sphere:
            codes.extend(sphere.okved)
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _queries(
    sphere_ids: list[str],
    phrase: str,
    extra_okved: list[str] | None = None,
    search_queries: list[str] | None = None,
) -> list[str]:
    jobs: list[str] = []

    # Named object first — don't burn minutes on generic «стадион» before the phrase.
    if phrase.strip():
        for q in expand_phrase_queries(phrase.strip()):
            jobs.append(q)

    for q in search_queries or []:
        text = (q or "").strip()
        if text:
            jobs.append(text)

    if not jobs:
        for sid in sphere_ids:
            sphere = SPHERES.get(sid)
            if not sphere:
                continue
            for q in sphere.queries:
                jobs.append(q)

    if extra_okved and not jobs:
        for code in extra_okved[:8]:
            title = title_for(code)
            if title:
                jobs.append(title.split(",")[0].strip())

    if not jobs:
        jobs.append("организация")

    # Dedupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for q in jobs:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(q)
    jobs = uniq

    # Schools: widen map queries so we find enough buildings for target N
    expanded: list[str] = []
    school_extra = (
        "средняя школа",
        "МБОУ школа",
        "лицей",
        "гимназия",
        "СОШ",
    )
    for q in jobs:
        expanded.append(q)
        low = q.lower().replace("ё", "е").strip()
        if low in {"школа", "школы"} or low == "школ":
            for extra in school_extra:
                expanded.append(extra)

    seen: set[str] = set()
    out: list[str] = []
    for q in expanded:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def _is_branch(item: dict[str, Any]) -> bool:
    data = item.get("data") or {}
    return (data.get("branch_type") or "").upper() == "BRANCH"


async def run_hunt(
    *,
    settings: Settings,
    database,
    user_id: int,
    sphere_ids: list[str],
    phrase: str,
    okved_raw: str,
    target_count: int,
    region: str,
    city: str,
    progress: Progress,
    kladr_id: str = "",
    hunt_id: int | None = None,
    search_queries: list[str] | None = None,
    cities: list[str] | None = None,
    regions: list[str] | None = None,
) -> dict[str, Any]:
    extra_okved = parse_okved(okved_raw)
    sel_cities, sel_regions, geo_label = parse_geo_selection(
        city=city,
        cities=cities,
        regions=list(regions or []) + ([region] if region.strip() else []),
    )
    city_store = ", ".join(sel_cities)
    region_store = ", ".join(sel_regions)
    if hunt_id is None:
        hunt_id = await db.create_hunt(
            database,
            user_id,
            phrase,
            sphere_ids,
            okved_raw,
            target_count,
            region=region_store,
            city=city_store,
        )
    emit = progress

    async def progress(text: str) -> None:
        await db.set_hunt_progress(database, hunt_id, text)
        await emit(text)
    dadata = DaData(settings.dadata_api_key)
    fns = FnsBfo()
    llm = RouterAI(
        settings.router_api_key,
        base_url=settings.router_base_url,
        model=settings.router_model,
        timeout=120.0,
    )
    found: list[dict[str, Any]] = []
    skipped = 0
    dropped = 0
    errors: list[str] = []
    # Only KP-done companies are excluded from future hunts
    kp_done = await db.kp_done_inns(database)
    already = len(kp_done)
    locations = dadata_locations_multi(sel_cities, sel_regions)
    prefixes = _okved_prefixes(sphere_ids, extra_okved)
    target_count = max(1, min(int(target_count), 50))
    geo_active = bool(sel_cities or sel_regions)
    cheap_mode = cheap_mode_enabled()

    async def take(
        item: dict[str, Any],
        *,
        found_via: str = "",
        soft: bool = False,
        from_building: bool = False,
    ) -> bool:
        nonlocal skipped
        if _is_branch(item):
            return False
        party = enrich_from_dadata(item)
        inn = party.get("inn") or ""
        if not inn:
            return False
        if any(str(p.get("inn") or "") == inn for p in found):
            return False
        if inn in kp_done:
            skipped += 1
            await db.add_result(database, hunt_id, inn, skipped=True)
            return False
        # Building→UK: intent already enforced by building + relation gates
        okved_code = str(party.get("okved") or "").strip()
        use_prefixes = [] if (soft or from_building or not okved_code) else prefixes
        if not from_building and not matches_search_intent(
            party.get("name") or "",
            phrase or found_via,
            okved=okved_code,
            okved_prefixes=use_prefixes,
        ):
            return False
        search_text = phrase or found_via
        city_mismatch = geo_active and not address_matches_geo(
            party.get("address") or "",
            sel_cities,
            sel_regions,
        )
        # Soft fill: keep geo filter — never pull other cities just to hit N
        if city_mismatch and not is_brand_query(search_text):
            return False
        if city_mismatch:
            party["geo_note"] = (
                "Юридический адрес не в выбранной географии; для сети ищем конкретные "
                "магазины, РЦ, склады или здания в выбранных городах/регионах."
            )
        sphere = sphere_ids[0] if sphere_ids else ""
        party["sphere"] = sphere
        party["idea"] = _idea(sphere_ids, phrase)
        party["source"] = "dadata"
        party["found_via"] = found_via
        if soft:
            party["found_via"] = f"{found_via} · soft".strip(" ·")
        if from_building:
            party["found_via"] = f"{party.get('found_via') or found_via} · здание".strip(" ·")
        await db.save_company(database, party)
        await db.add_result(database, hunt_id, inn, skipped=False)
        found.append(party)
        return True

    try:
        jobs = _queries(
            sphere_ids, phrase, extra_okved, search_queries=search_queries
        )
        sphere0 = sphere_ids[0] if sphere_ids else ""
        query_main = (
            phrase.strip()
            or ((search_queries or [""])[0] if search_queries else "")
            or (jobs[0] if jobs else "объект")
        ).strip()

        oneshot_seed: list[dict[str, Any]] = []
        if llm_oneshot_enabled() and llm.available:
            await progress(
                f"Охота #{hunt_id}\n"
                f"Где: {geo_label}\n"
                f"Нужно карточек: {target_count}\n"
                f"Режим: один LLM-запрос -> сразу карточки.\n"
                f"Запрос: «{query_main}»"
            )
            oneshot_cards: list[dict[str, Any]] = []
            try:
                oneshot_cards = await asyncio.wait_for(
                    build_cards_oneshot(
                        llm,
                        query=query_main,
                        city=geo_label or city_store or "",
                        count=target_count,
                        sphere=sphere0,
                        idea=_idea(sphere_ids, phrase),
                        dadata=dadata,
                        fns=fns,
                    ),
                    timeout=110.0,
                )
            except asyncio.TimeoutError:
                errors.append("llm-oneshot: timeout")
                await progress("LLM oneshot: таймаут — запасной пайплайн…")
            except Exception as exc:
                log.exception("llm oneshot failed")
                errors.append(f"llm-oneshot: {exc}")
                await progress(f"LLM oneshot ошибка — запасной пайплайн: {exc}")

            verified_oneshot: list[dict[str, Any]] = []
            for card in oneshot_cards:
                inn = str(card.get("inn") or "")
                if not inn:
                    continue
                if inn in kp_done:
                    skipped += 1
                    await db.add_result(database, hunt_id, inn, skipped=True)
                    continue
                if any(str(p.get("inn") or "") == inn for p in verified_oneshot):
                    continue
                card["stamp_label"] = stamp_label(
                    str(card.get("stamp") or ""), int(card.get("score") or 0)
                )
                # Persist full card blob so КП/история видят контакты и объект.
                card_payload = {
                    k: v
                    for k, v in card.items()
                    if k not in {"payload"}
                }
                await db.save_company(
                    database,
                    {
                        **card,
                        "payload": card_payload,
                        "source": "llm_oneshot",
                    },
                )
                await db.update_company(
                    database,
                    inn,
                    {
                        "name": card.get("name"),
                        "ogrn": card.get("ogrn"),
                        "okved": card.get("okved"),
                        "address": card.get("address"),
                        "status": card.get("status"),
                        "management": card.get("management_label")
                        or card.get("management"),
                        "stamp": card.get("stamp"),
                        "score": card.get("score"),
                        "idea": card.get("idea"),
                        "payload_json": json.dumps(card_payload, ensure_ascii=False),
                    },
                )
                await db.add_result(database, hunt_id, inn, skipped=False)
                verified_oneshot.append(card)
                if len(verified_oneshot) >= target_count:
                    break

            if verified_oneshot:
                await progress(
                    f"LLM oneshot: найдено объектов {len(verified_oneshot)}/{target_count} — "
                    "дальше ищем владельцев/людей/личные контакты"
                )
                oneshot_seed = list(verified_oneshot)
                for card in oneshot_seed:
                    if not any(str(p.get("inn") or "") == str(card.get("inn") or "") for p in found):
                        found.append(card)
                await progress(
                    f"LLM oneshot дал {len(verified_oneshot)} объект(ов). "
                    "Запускаем обязательную сверку людей и личных каналов…"
                )
            else:
                await progress(
                    "LLM oneshot пусто — запасной пайплайн (карты/DaData)…"
                )

        await progress(
            f"Охота #{hunt_id}\n"
            f"Где: {geo_label}\n"
            f"Нужно зданий с собственником: {target_count}\n"
            f"Уже в КП: {already} — их не берём.\n"
            f"Уже от oneshot: {len(oneshot_seed)}. "
            f"Добор: здание -> юрлицо -> контакты -> LLM-аудит."
        )
        object_hits = 0
        http = httpx.AsyncClient(
            timeout=18.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )

        query_hint = phrase.strip() or ((search_queries or [""])[0] if search_queries else "")
        used_buildings: set[str] = set()
        buildings_seen = 0
        buildings_rejected = 0
        owners_rejected = 0

        async def attach_object(
            party: dict[str, Any],
            obj: dict[str, Any],
            rec: dict[str, Any],
            *,
            with_photos: bool = True,
            rel_hint: dict[str, Any] | None = None,
        ) -> None:
            title = str(obj.get("title") or "")
            if is_tenant_inside_host(title):
                return
            if is_generic_object_title(title, query_hint):
                return
            addr = str(obj.get("address") or "").strip()
            legal = str(party.get("address") or "").strip()
            if not streetish_address(addr) and streetish_address(legal):
                addr = legal
                obj = {**obj, "address": addr}
            title_now = str(obj.get("title") or "").strip()
            maps = str(obj.get("maps_yandex") or "")
            # Keep real /org/ cards. Only synthesize text= pin when maps is empty/search.
            org_maps = bool(maps) and "/org/" in maps and "text=" not in maps
            if (
                not org_maps
                and (not maps or "text=" in maps)
                and title_now
                and streetish_address(addr)
            ):
                pin = f"{title_now} {addr}"
                obj = {
                    **obj,
                    "maps_yandex": f"https://yandex.ru/maps/?text={quote_plus(pin)}",
                    "maps_google": (
                        "https://www.google.com/maps/search/?api=1&query="
                        + quote_plus(pin)
                    ),
                }
            rel = object_company_relation(party, obj)
            # Keep soft «из источника» when hard relation is weak — product rule
            if rel_hint and relation_usable(rel_hint, allow_source=True):
                if not relation_accepted(rel, min_score=MIN_RELATION_CONFIDENCE):
                    rel = dict(rel_hint)
                elif rel_hint.get("soft"):
                    rel = {
                        **rel,
                        "found_via": rel_hint.get("found_via") or rel.get("found_via"),
                        "found_query": rel_hint.get("found_query") or "",
                    }
            photo_notes: list[str] = []
            photos: list[str] = []
            title_for_photo = str(obj.get("title") or "")
            soft_photo = is_school_building_title(title_for_photo) or is_sports_building_title(
                title_for_photo
            )
            photo_ok = relation_usable(
                rel,
                min_score=(
                    MIN_RELATION_CONFIDENCE
                    if soft_photo
                    else MIN_PHOTO_RELATION_CONFIDENCE
                ),
                allow_source=True,
            ) or relation_accepted(
                rel,
                min_score=MIN_RELATION_CONFIDENCE if soft_photo else MIN_PHOTO_RELATION_CONFIDENCE,
            )
            if with_photos and photo_ok:
                photo_obj = {
                    **obj,
                    "city": (obj.get("city") or (sel_cities[0] if sel_cities else "") or ""),
                }
                photos, photo_notes = await collect_object_photos(http, photo_obj)
            elif with_photos:
                photo_notes = [
                    "Фото: ищем по названию/картам даже при мягкой связи"
                ]
                photo_obj = {
                    **obj,
                    "city": (obj.get("city") or (sel_cities[0] if sel_cities else "") or ""),
                }
                try:
                    photos, photo_notes = await collect_object_photos(http, photo_obj)
                except Exception:
                    photos, photo_notes = [], ["фото не удалось собрать"]
            party["object"] = {
                "title": obj.get("title") or "",
                "address": obj.get("address") or "",
                "source": obj.get("source") or "",
                "url_2gis": obj.get("url_2gis") or "",
                "url_osm": obj.get("url_osm") or "",
                "maps_yandex": obj.get("maps_yandex") or "",
                "maps_google": obj.get("maps_google") or "",
                "recommend": rec,
                "relation": rel,
                "photo_notes": photo_notes,
                "verified": True,
            }
            party["photos"] = photos
            if obj.get("address"):
                party["object_address"] = obj["address"]

        async def pick_owner_for_building(
            obj: dict[str, Any], *, query: str
        ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
            """Multi-path owner/UK discovery, then relation gate."""
            name_q = str(obj.get("title") or "").strip()
            city_q = str(obj.get("city") or "").strip() or (
                sel_cities[0] if sel_cities else ""
            )
            try:
                cands = await asyncio.wait_for(
                    resolve_building_owners(
                        http=http,
                        dadata=dadata,
                        obj=obj,
                        locations=locations,
                        city=city_q,
                        llm=llm,
                    ),
                    timeout=8.0 if cheap_mode else 55.0,
                )
            except asyncio.TimeoutError:
                log.warning("resolve_building_owners timeout for %s", name_q)
                errors.append(f"owners timeout {name_q}")
                cands = []
            except Exception as exc:
                log.exception("resolve_building_owners failed for %s", name_q)
                errors.append(f"owners {name_q}: {exc}")
                cands = []
            if cands:
                await progress(
                    f"Собственник «{name_q}»: {candidate_sources_summary(cands)}"
                )
            seen_inn: set[str] = set()
            best_soft: tuple[int, Any, dict[str, Any] | None] = (-1, None, None)
            for cand in cands:
                inn = str(cand.get("inn") or "")
                if inn and inn in seen_inn:
                    continue
                if inn:
                    seen_inn.add(inn)
                suggest = cand.get("suggest")
                if not suggest:
                    continue
                party_probe = candidate_party(cand) or enrich_from_dadata(suggest)
                party_probe["owner_source"] = cand.get("source") or ""
                cand["party"] = {
                    "name": party_probe.get("name"),
                    "address": party_probe.get("address"),
                    "okved": party_probe.get("okved"),
                }
                rel = object_company_relation(party_probe, obj)
                try:
                    conf = int((rel or {}).get("confidence") or 0)
                except (TypeError, ValueError):
                    conf = 0
                resolver_score = int(cand.get("resolver_score") or 0)
                soft_score = max(conf, resolver_score)
                if soft_score > best_soft[0]:
                    soft_rel = {
                        **(rel if isinstance(rel, dict) else {}),
                        "status": "из источника (связь не доказана)",
                        "confidence": min(max(soft_score, 20), 49),
                        "role": "кандидат из реестра/поиска",
                        "reason": "; ".join(
                            list(cand.get("resolver_reasons") or [])
                            or [str((rel or {}).get("reason") or "ИНН из открытого источника")]
                        )[:400],
                        "soft": True,
                        "found_via": cand.get("source") or "",
                        "found_query": cand.get("query") or query,
                    }
                    best_soft = (soft_score, suggest, soft_rel)
                if relation_accepted(rel, min_score=MIN_RELATION_CONFIDENCE):
                    if isinstance(rel, dict):
                        rel = {
                            **rel,
                            "found_via": cand.get("source") or "",
                            "found_query": cand.get("query") or query,
                        }
                    return suggest, rel, cands
            # Product rule: take best source candidate even without hard proof
            if best_soft[1] is not None and best_soft[0] >= 20:
                log.info(
                    "soft-accept owner for %s score=%s",
                    name_q,
                    best_soft[0],
                )
                return best_soft[1], best_soft[2], cands
            return None, None, cands

        async def keep_building_without_owner(
            obj: dict[str, Any],
            rec: dict[str, Any],
            *,
            query: str,
            owner_cands: list[dict[str, Any]] | None = None,
        ) -> bool:
            title = str(obj.get("title") or "").strip()
            addr = str(obj.get("address") or "").strip()
            if not title:
                return False
            pseudo_inn = _object_card_id(title, addr)
            if pseudo_inn in kp_done or any(str(p.get("inn") or "") == pseudo_inn for p in found):
                return False
            maps = str(obj.get("maps_yandex") or "")
            org_maps = bool(maps) and "/org/" in maps and "text=" not in maps
            if (
                not org_maps
                and title
                and addr
                and (not maps or "text=" in maps or "pt=" in maps)
            ):
                pin = f"{title} {addr}".strip()
                obj = {
                    **obj,
                    "maps_yandex": f"https://yandex.ru/maps/?text={quote_plus(pin)}",
                    "maps_google": (
                        "https://www.google.com/maps/search/?api=1&query="
                        + quote_plus(pin)
                    ),
                }
            try:
                photos, photo_notes = await collect_object_photos(
                    http,
                    {
                        **obj,
                        "city": (obj.get("city") or (sel_cities[0] if sel_cities else "") or ""),
                    },
                )
            except Exception:
                photos, photo_notes = [], ["фото не удалось собрать"]
            rel = {
                "status": "владелец не найден",
                "confidence": 10,
                "role": "собственник/оператор требует проверки",
                "reason": "здание найдено, но юрлицо не подтвердилось в быстрых источниках",
                "soft": True,
                "found_via": "object-only",
                "found_query": query,
            }
            party = {
                "inn": pseudo_inn,
                "ogrn": "",
                "name": title,
                "okved": "",
                "address": addr,
                "status": "",
                "management": "",
                "sphere": sphere0,
                "idea": _idea(sphere_ids, phrase),
                "source": "object_only",
                "found_via": f"{query} · объект без юрлица",
                "object_address": addr,
                "object": {
                    "title": title,
                    "address": addr,
                    "source": obj.get("source") or "maps",
                    "url_2gis": obj.get("url_2gis") or "",
                    "url_osm": obj.get("url_osm") or "",
                    "maps_yandex": obj.get("maps_yandex") or "",
                    "maps_google": obj.get("maps_google") or "",
                    "recommend": rec,
                    "relation": rel,
                    "photo_notes": photo_notes,
                    "verified": False,
                },
                "photos": photos,
                "owner_candidates": owner_cands or [],
                "payload": {
                    "object_only": True,
                    "real_inn_missing": True,
                },
            }
            await db.save_company(database, party)
            await db.add_result(database, hunt_id, pseudo_inn, skipped=False)
            found.append(party)
            return True

        try:
            for query in jobs:
                if len(found) >= target_count:
                    break
                await progress(
                    f"Поиск зданий «{query}» в {geo_label}… "
                    f"принято {len(found)}/{target_count}"
                )

                try:
                    objects = await search_objects(
                        http,
                        query=query,
                        cities=sel_cities
                        or (
                            [
                                c
                                for c in (
                                    city_store.split(",") if city_store else []
                                )
                                if c.strip()
                            ]
                        ),
                        limit=max(
                            target_count
                            * (
                                3
                                if sphere0 == "social"
                                else (2 if cheap_mode else 3)
                            ),
                            10 if cheap_mode else (20 if sphere0 == "social" else 12),
                        ),
                    )
                except Exception as exc:
                    log.exception("object search failed for %s", query)
                    errors.append(f"объекты {query}: {exc}")
                    objects = []

                # Keep a few spare buildings: final LLM audit may reject bad glue.
                found_budget = target_count if cheap_mode else target_count + min(3, max(1, target_count))
                for obj in objects:
                    if len(found) >= found_budget:
                        break
                    title = str(obj.get("title") or "")
                    addr = str(obj.get("address") or "")
                    gate = accept_building_candidate(
                        title=title,
                        address=addr,
                        query=query,
                        sphere=sphere0,
                    )
                    buildings_seen += 1
                    if not gate.get("ok"):
                        buildings_rejected += 1
                        continue
                    bkey = building_dedupe_key(title, addr)
                    if bkey in used_buildings:
                        buildings_rejected += 1
                        continue
                    rec = gate.get("rec") or recommend_object(
                        title=title,
                        address=addr,
                        query=query,
                        sphere=sphere0,
                    )
                    object_hits += 1
                    await progress(
                        f"Здание ок: «{title}» -> ищем собственника/УК "
                        f"({len(found)}/{target_count})"
                    )
                    owner_item, rel, owner_cands = await pick_owner_for_building(
                        obj, query=query
                    )
                    if not owner_item or not rel:
                        owners_rejected += 1
                        kept = await keep_building_without_owner(
                            obj,
                            rec,
                            query=query,
                            owner_cands=owner_cands,
                        )
                        if kept:
                            used_buildings.add(bkey)
                            await progress(
                                f"Юрлицо для «{title}» не найдено — карточку оставили для проверки"
                            )
                        else:
                            await progress(
                                f"Юрлицо для «{title}» не найдено — объект уже был в выдаче"
                            )
                        continue
                    before = len(found)
                    ok = await take(
                        owner_item, found_via=query, from_building=True
                    )
                    if not ok or len(found) <= before:
                        owners_rejected += 1
                        kept = await keep_building_without_owner(
                            obj,
                            rec,
                            query=query,
                            owner_cands=owner_cands,
                        )
                        if kept:
                            used_buildings.add(bkey)
                            await progress(
                                f"Юрлицо для «{title}» не прошло фильтр — карточку здания оставили"
                            )
                        continue
                    await attach_object(
                        found[-1], obj, rec, with_photos=True, rel_hint=rel
                    )
                    found[-1]["owner_candidates"] = owner_cands or []
                    # Soft product gate: keep source candidates; only drop empty relation
                    final_rel = (found[-1].get("object") or {}).get("relation") or rel
                    if not relation_usable(
                        final_rel, min_score=MIN_RELATION_CONFIDENCE, allow_source=True
                    ):
                        owners_rejected += 1
                        obj_saved = found[-1].get("object") if isinstance(found[-1].get("object"), dict) else {}
                        obj_saved["relation"] = {
                            **(final_rel if isinstance(final_rel, dict) else {}),
                            "status": "связь требует проверки",
                            "confidence": int((final_rel or {}).get("confidence") or 20) if isinstance(final_rel, dict) else 20,
                            "soft": True,
                        }
                        found[-1]["object"] = obj_saved
                        await progress(
                            f"Связь с «{title}» слабая — карточку оставили для проверки"
                        )
                    used_buildings.add(bkey)
                    await asyncio.sleep(0.05)

                await asyncio.sleep(0.05)

            if len(found) < target_count:
                if sphere0 in _COMPANY_ADDRESS_FALLBACK_SPHERES:
                    await progress(
                        f"Картами найдено мало объектов: {len(found)} из {target_count}. "
                        f"Пробуем добор по действующим компаниям с адресом…"
                    )
                    for query in jobs:
                        if len(found) >= target_count:
                            break
                        try:
                            suggestions = await dadata.suggest(
                                query,
                                count=min(20, max(6, target_count * 4)),
                                okved=prefixes,
                                locations=locations,
                            )
                        except Exception as exc:
                            log.exception("fallback dadata failed for %s", query)
                            errors.append(f"добор {query}: {exc}")
                            suggestions = []
                        for item in suggestions:
                            if len(found) >= target_count:
                                break
                            party_probe = enrich_from_dadata(item)
                            addr = str(party_probe.get("address") or "")
                            if not streetish_address(addr):
                                continue
                            before = len(found)
                            ok = await take(
                                item,
                                found_via=f"{query} · юрадрес",
                                soft=True,
                                from_building=True,
                            )
                            if not ok or len(found) <= before:
                                continue
                            picked = found[-1]
                            title = short_company_label(str(picked.get("name") or "")) or query
                            pin = f"{title} {addr}".strip()
                            picked["object_address"] = addr
                            picked["object"] = {
                                "title": title,
                                "address": addr,
                                "source": "dadata_legal_address_fallback",
                                "url_2gis": "",
                                "url_osm": "",
                                "maps_yandex": f"https://yandex.ru/maps/?text={quote_plus(pin)}",
                                "maps_google": (
                                    "https://www.google.com/maps/search/?api=1&query="
                                    + quote_plus(pin)
                                ),
                                "recommend": {
                                    "ok": True,
                                    "score": 45,
                                    "reason": "карты не нашли отдельный объект; взят адрес действующей компании",
                                    "status": "перепроверить",
                                },
                                "relation": {
                                    "status": "адрес компании как объект-кандидат",
                                    "confidence": 35,
                                    "role": "компания/оператор; здание нужно проверить по карте",
                                    "reason": "fallback по DaData после пустого поиска объектов на картах",
                                    "soft": True,
                                    "found_via": "dadata",
                                    "found_query": query,
                                },
                                "photo_notes": [
                                    "фото фасада не подтверждено: объект взят по юридическому адресу",
                                ],
                                "verified": False,
                            }
                            picked["photos"] = []

                if len(found) < target_count:
                    await progress(
                        f"Строго по зданиям: принято {len(found)} из {target_count}. "
                        f"Добор «любыми компаниями» отключён."
                    )
                else:
                    await progress(
                        f"Добор по адресам дал {len(found)} карточку(и); "
                        f"они помечены как требующие проверки здания."
                    )
        finally:
            await http.aclose()

        await progress(
            f"Здания: просмотрено {buildings_seen}, отсеяно {buildings_rejected}, "
            f"без подтверждённого юрлица {owners_rejected}. "
            f"В работу: {len(found)} (уже в КП пропуск {skipped}).\n"
            f"Дальше — выписки и контакты только по принятым зданиям…"
        )

        verified: list[dict[str, Any]] = []
        for i, party in enumerate(found, start=1):
            if len(verified) >= target_count:
                break
            inn = party["inn"]
            object_only = str(inn).startswith("OBJ-") or bool(
                (party.get("payload") or {}).get("object_only")
                if isinstance(party.get("payload"), dict)
                else False
            )
            obj0 = party.get("object") if isinstance(party.get("object"), dict) else {}
            rel0 = obj0.get("relation") if isinstance(obj0, dict) else {}
            if not obj0:
                dropped += 1
                await progress(
                    f"Пропуск {inn}: нет данных здания — карточку собрать нельзя"
                )
                continue
            if not relation_usable(
                rel0 if isinstance(rel0, dict) else {},
                min_score=MIN_RELATION_CONFIDENCE,
                allow_source=True,
            ):
                rel0 = {
                    **(rel0 if isinstance(rel0, dict) else {}),
                    "status": "связь требует проверки",
                    "confidence": int((rel0 or {}).get("confidence") or 20) if isinstance(rel0, dict) else 20,
                    "soft": True,
                }
                obj0["relation"] = rel0
                party["object"] = obj0
            if object_only:
                await progress(
                    f"Агент 2: добираем собственника для объекта — {obj0.get('title') or inn}"
                )
                city_q = str(obj0.get("city") or "").strip() or (
                    sel_cities[0] if sel_cities else ""
                )
                owner_cands: list[dict[str, Any]] = []
                try:
                    async with httpx.AsyncClient(
                        timeout=18.0,
                        follow_redirects=True,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/120.0.0.0 Safari/537.36"
                            ),
                            "Accept-Language": "ru-RU,ru;q=0.9",
                        },
                    ) as owner_http:
                        owner_cands = await asyncio.wait_for(
                            resolve_building_owners(
                                http=owner_http,
                                dadata=dadata,
                                obj={**obj0, "city": city_q},
                                locations=locations,
                                city=city_q,
                                llm=llm,
                            ),
                            timeout=12.0 if cheap_mode else 55.0,
                        )
                except asyncio.TimeoutError:
                    log.warning("oneshot owner resolver timeout for %s", obj0.get("title") or inn)
                    errors.append(f"owners timeout {obj0.get('title') or inn}")
                except Exception as exc:
                    log.exception("oneshot owner resolver failed for %s", obj0.get("title") or inn)
                    errors.append(f"owners {obj0.get('title') or inn}: {exc}")
                if owner_cands:
                    party["owner_candidates"] = owner_cands
                    await progress(
                        f"Собственник «{obj0.get('title') or inn}»: "
                        f"{candidate_sources_summary(owner_cands)}"
                    )
                if not owner_cands:
                    title_q = str(obj0.get("title") or "").strip()
                    city_q = str(obj0.get("city") or "").strip() or (
                        sel_cities[0] if sel_cities else ""
                    )
                    dadata_queries = [
                        f"{title_q} {city_q}".strip(),
                        title_q,
                    ]
                    seen_suggest_inn: set[str] = set()
                    for dq in [q for q in dadata_queries if q]:
                        try:
                            suggestions = await dadata.suggest(
                                dq,
                                count=8,
                                locations=locations,
                            )
                        except Exception as exc:
                            log.info("object-only dadata suggest failed %s: %s", dq, exc)
                            continue
                        for suggest in suggestions:
                            probe = enrich_from_dadata(suggest)
                            sug_inn = str(probe.get("inn") or "").strip()
                            if not sug_inn or sug_inn in seen_suggest_inn:
                                continue
                            seen_suggest_inn.add(sug_inn)
                            rel_probe = object_company_relation(probe, obj0)
                            rel_conf = int((rel_probe or {}).get("confidence") or 0)
                            if rel_conf < 35:
                                continue
                            owner_cands.append(
                                {
                                    "inn": sug_inn,
                                    "suggest": suggest,
                                    "source": "dadata-object-title",
                                    "query": dq,
                                    "resolver_score": rel_conf,
                                    "resolver_reasons": [
                                        f"DaData suggest по названию объекта: {dq}",
                                        str((rel_probe or {}).get("reason") or ""),
                                    ],
                                    "party": {
                                        "name": probe.get("name"),
                                        "address": probe.get("address"),
                                        "okved": probe.get("okved"),
                                    },
                                }
                            )
                        if owner_cands:
                            party["owner_candidates"] = owner_cands
                            await progress(
                                f"Собственник «{title_q or inn}» через DaData: "
                                f"{candidate_sources_summary(owner_cands)}"
                            )
                            break
                for cand in owner_cands:
                    suggest = cand.get("suggest")
                    if not suggest:
                        continue
                    probe = candidate_party(cand) or enrich_from_dadata(suggest)
                    if not str(probe.get("inn") or "").strip():
                        continue
                    cand["party"] = {
                        "name": probe.get("name"),
                        "address": probe.get("address"),
                        "okved": probe.get("okved"),
                    }
                    rel_probe = object_company_relation(probe, obj0)
                    resolver_score = int(cand.get("resolver_score") or 0)
                    if relation_usable(rel_probe, allow_source=True) or resolver_score >= MIN_RELATION_CONFIDENCE:
                        probe["object"] = {
                            **obj0,
                            "relation": (
                                rel_probe
                                if relation_usable(rel_probe, allow_source=True)
                                else {
                                    "status": "найден в источниках",
                                    "confidence": min(max(resolver_score, 50), 80),
                                    "source": cand.get("source") or "",
                                    "soft": True,
                                }
                            ),
                        }
                        probe["photos"] = party.get("photos") or []
                        probe["object_address"] = party.get("object_address") or obj0.get("address") or ""
                        probe["owner_candidates"] = owner_cands
                        probe["sphere"] = party.get("sphere") or ""
                        probe["idea"] = party.get("idea") or ""
                        probe["found_via"] = party.get("found_via") or "oneshot owner resolver"
                        party = {**party, **probe}
                        inn = str(party.get("inn") or inn)
                        object_only = str(inn).startswith("OBJ-") or not bool(inn)
                        obj0 = party.get("object") if isinstance(party.get("object"), dict) else obj0
                        break
            if object_only:
                await progress(f"Агент 2: карточка объекта без ИНН — {obj0.get('title') or inn}")
                flat = {
                    **party,
                    "management_label": "ЛПР не найден",
                    "management_post": "Нужно определить владельца/оператора",
                    "payload": {
                        **(party.get("payload") or {}),
                        "object_only": True,
                        "real_inn_missing": True,
                    },
                }
            else:
                await progress(f"Агент 2: выписка {i} из {len(found)} — ИНН {inn}")
                try:
                    raw = await dadata.find_by_inn(inn)
                except Exception as exc:
                    log.exception("DaData findById failed for %s", inn)
                    errors.append(f"выписка {inn}: {exc}")
                    flat = {
                        **party,
                        "stamp": "осторожно",
                        "score": 40,
                        "stamp_hint": "DaData не отдала выписку; карточка оставлена для ручной проверки",
                    }
                else:
                    if raw:
                        flat = enrich_from_dadata(raw)
                    else:
                        flat = {
                            **party,
                            "stamp": "осторожно",
                            "score": 40,
                            "stamp_hint": "Выписка по ИНН не найдена; карточка оставлена для ручной проверки",
                        }
            flat["search_phrase"] = phrase.strip() or party.get("found_via") or ""
            flat["requested_city"] = city_store or geo_label
            flat["geo_note"] = party.get("geo_note") or ""
            flat["sphere"] = party.get("sphere") or ""
            flat["idea"] = party.get("idea") or ""
            flat["object"] = party.get("object") or {}
            flat["photos"] = list(party.get("photos") or [])
            if party.get("object_address"):
                flat["object_address"] = party["object_address"]
            # After full ЕГРЮЛ address: pin object to street/house, not «ТЦ Казань»
            obj_meta = dict(flat.get("object") or {})
            legal = str(flat.get("address") or "")
            obj_addr = str(obj_meta.get("address") or flat.get("object_address") or "")
            title_o = str(obj_meta.get("title") or short_company_label(flat.get("name") or "") or "")
            if streetish_address(legal) and not streetish_address(obj_addr):
                obj_meta["address"] = legal
                flat["object_address"] = legal
                pin = f"{title_o} {legal}".strip()
                obj_meta["maps_yandex"] = f"https://yandex.ru/maps/?text={quote_plus(pin)}"
                obj_meta["maps_google"] = (
                    "https://www.google.com/maps/search/?api=1&query=" + quote_plus(pin)
                )
                flat["object"] = obj_meta
                if not flat.get("photos"):
                    try:
                        async with httpx.AsyncClient(
                            timeout=18.0,
                            follow_redirects=True,
                            headers={
                                "User-Agent": (
                                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/120.0.0.0 Safari/537.36"
                                )
                            },
                        ) as photo_http:
                            more_photos, more_notes = await collect_object_photos(
                                photo_http,
                                {
                                    **obj_meta,
                                    "city": (sel_cities[0] if sel_cities else ""),
                                },
                            )
                    except Exception:
                        more_photos, more_notes = [], []
                    if more_photos:
                        flat["photos"] = more_photos
                        obj_meta["photo_notes"] = more_notes
                        flat["object"] = obj_meta
            if not object_only:
                flat = await merge_fns_finance(flat, fns)
            await progress(
                f"Агент 2+3: контакты и проверка — {'объект без ИНН' if object_only else 'ИНН ' + inn}"
            )
            try:
                flat = await asyncio.wait_for(
                    enrich_contacts(flat, llm=llm),
                    timeout=35.0 if object_only else 90.0,
                )
            except asyncio.TimeoutError:
                log.warning("enrich_contacts timeout for %s", inn)
                presence = flat.get("presence") or {}
                checks = list(presence.get("checks") or [])
                checks.append("Контакты: таймаут обогащения — карточку оставили без глубокой сверки")
                presence["checks"] = checks
                flat["presence"] = presence
            except Exception as exc:
                log.exception("enrich_contacts failed for %s", inn)
                errors.append(f"контакты {inn}: {exc}")
            flat["search_phrase"] = phrase.strip() or party.get("found_via") or ""
            flat["requested_city"] = city_store or geo_label
            flat["geo_note"] = party.get("geo_note") or ""
            flat["sphere"] = party.get("sphere") or ""
            flat["idea"] = party.get("idea") or ""
            if party.get("object"):
                # Keep hunt building; don't let company-name invent overwrite it.
                base = dict(party["object"])
                cur = flat.get("object") if isinstance(flat.get("object"), dict) else {}
                if cur:
                    # Prefer streetish address from either side
                    if streetish_address(str(cur.get("address") or "")) and not streetish_address(
                        str(base.get("address") or "")
                    ):
                        base["address"] = cur["address"]
                    for key in ("maps_yandex", "maps_google", "url_2gis", "url_osm"):
                        if cur.get(key) and not base.get(key):
                            base[key] = cur[key]
                flat["object"] = base
                if party.get("photos") and not flat.get("photos"):
                    flat["photos"] = party["photos"]
                _filter_object_photos(flat)
            qualification = qualify_lead(flat)
            flat["qualification"] = qualification
            # KP is a separate later step — do not auto-compose during hunt
            flat["kp"] = {}
            flat["kp_status"] = "отложено"
            if qualification.get("non_object_legal_entity") and not object_only:
                presence = flat.get("presence") or {}
                checks = list(presence.get("checks") or [])
                checks.append("Объект: фото скрыты, потому что юрлицо не подтверждено как владелец/оператор здания")
                presence["checks"] = checks
                presence["photos"] = {"status": "нет", "value": []}
                flat["presence"] = presence
                flat["photos"] = []
                workflow = qualification.get("object_workflow") or {}
                object_routes = [
                    {
                        "title": str(item.get("title") or ""),
                        "url": str(item.get("url") or ""),
                        "hint": str(item.get("hint") or ""),
                        "status": "открыть",
                    }
                    for item in (workflow.get("routes") or [])
                    if isinstance(item, dict) and item.get("url")
                ]
                if list_org_url := next(
                    (
                        item
                        for item in flat.get("contact_routes", [])
                        if item.get("title") == "List-Org"
                    ),
                    None,
                ):
                    object_routes.append(list_org_url)
                flat["contact_routes"] = object_routes
            score, stamp, stamp_hint = _score(
                party.get("sphere") or "",
                flat.get("status") or "",
                bool(flat.get("management")),
                online_hits=int(flat.get("online_hits") or 0),
                has_finance=flat.get("revenue") is not None or flat.get("profit") is not None,
                object_confirmed=bool(qualification.get("object_confirmed")),
                non_object_legal_entity=bool(qualification.get("non_object_legal_entity")),
            )
            flat["stamp"] = stamp
            flat["score"] = score
            flat["stamp_hint"] = stamp_hint
            flat["owner_candidates"] = party.get("owner_candidates") or flat.get(
                "owner_candidates"
            ) or []
            if object_only:
                presence = flat.get("presence") if isinstance(flat.get("presence"), dict) else {}
                checks = list(presence.get("checks") or [])
                checks.append("Карточка сохранена без подтверждённого ИНН: нужно проверить владельца/оператора")
                presence["checks"] = checks
                flat["presence"] = presence
                flat["card_audit"] = {
                    "verdict": "warn",
                    "reason": "Здание найдено, но владелец/оператор не подтверждён в быстрых источниках",
                    "keep_card": True,
                }
            else:
                await progress(f"LLM-аудит карточки — ИНН {inn}")

            async def _ensure_owner_candidates() -> list[dict[str, Any]]:
                obj = flat.get("object") if isinstance(flat.get("object"), dict) else {}
                if not obj.get("title"):
                    return list(flat.get("owner_candidates") or [])
                city_q = (
                    str(obj.get("city") or "").strip()
                    or (sel_cities[0] if sel_cities else "")
                    or city_store
                    or ""
                )
                async with httpx.AsyncClient(
                    timeout=20.0,
                    follow_redirects=True,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (compatible; NiteosHunt/1.0; +https://niteos.local)"
                        )
                    },
                ) as refresh_http:
                    return await resolve_building_owners(
                        http=refresh_http,
                        dadata=dadata,
                        obj=obj,
                        locations=locations,
                        city=city_q,
                        llm=None,
                    )

            if object_only:
                audit = flat["card_audit"]
            else:
                try:
                    audit = await asyncio.wait_for(
                        run_final_card_audit(
                            llm,
                            flat,
                            query=phrase.strip() or party.get("found_via") or "",
                            city=city_store or geo_label,
                            dadata=dadata,
                            fns=fns,
                            candidates=flat.get("owner_candidates") or [],
                            ensure_candidates=_ensure_owner_candidates,
                        ),
                        timeout=55.0,
                    )
                except asyncio.TimeoutError:
                    log.warning("card audit timeout for %s", inn)
                    audit = None
                except Exception as exc:
                    log.exception("card audit failed for %s", inn)
                    errors.append(f"llm-аудит {inn}: {exc}")
                    audit = None
            if audit:
                inn = str(flat.get("inn") or inn)
                # Re-qualify after possible INN swap / contact clears.
                qualification = qualify_lead(flat)
                flat["qualification"] = qualification
                if audit.get("verdict") == "accept" and not audit.get("swapped"):
                    score, stamp, stamp_hint = _score(
                        party.get("sphere") or flat.get("sphere") or "",
                        flat.get("status") or "",
                        bool(flat.get("management")),
                        online_hits=int(flat.get("online_hits") or 0),
                        has_finance=flat.get("revenue") is not None
                        or flat.get("profit") is not None,
                        object_confirmed=bool(qualification.get("object_confirmed")),
                        non_object_legal_entity=bool(
                            qualification.get("non_object_legal_entity")
                        ),
                    )
                    flat["stamp"] = stamp
                    flat["score"] = score
                    flat["stamp_hint"] = stamp_hint or flat.get("stamp_hint") or ""
                else:
                    # warn / swap: keep audit stamp (осторожно), never стоп
                    stamp = str(flat.get("stamp") or "осторожно")
                    if stamp == "стоп":
                        stamp = "осторожно"
                        flat["stamp"] = stamp
                    try:
                        score = int(flat.get("score") or score)
                    except (TypeError, ValueError):
                        pass
                    stamp_hint = str(flat.get("stamp_hint") or stamp_hint)
                await progress(
                    f"LLM-аудит ИНН {inn}: {audit.get('verdict')}"
                    f"{' · замена юрлица' if audit.get('swapped') else ''} — "
                    f"{str(audit.get('reason') or '')[:160]}"
                )
            await db.update_company(
                database,
                inn,
                {
                    "name": flat["name"] or party["name"],
                    "ogrn": flat.get("ogrn"),
                    "okved": flat.get("okved"),
                    "address": flat.get("address"),
                    "status": flat.get("status"),
                    "management": flat.get("management_label") or flat.get("management"),
                    "stamp": stamp,
                    "score": score,
                    "idea": party.get("idea"),
                    "payload_json": json.dumps(
                        {
                            **(flat.get("payload") or {}),
                            "management_post": flat.get("management_post"),
                            "founders": flat.get("founders") or [],
                            "founders_detail": flat.get("founders_detail") or [],
                            "managers": flat.get("managers") or [],
                            "employee_count": flat.get("employee_count"),
                            "phones": flat.get("phones") or [],
                            "phone_sources": (
                                (flat.get("presence") or {}).get("phone_sources")
                                if isinstance(flat.get("presence"), dict)
                                else []
                            ),
                            "emails": flat.get("emails") or [],
                            "sites": flat.get("sites") or [],
                            "photos": flat.get("photos") or [],
                            "people_contacts": flat.get("people_contacts") or [],
                            "contact_routes": flat.get("contact_routes") or [],
                            "presence": flat.get("presence") or {},
                            "kp": flat.get("kp") or {},
                            "kp_status": flat.get("kp_status") or "отложено",
                            "object": flat.get("object") or {},
                            "object_address": flat.get("object_address") or "",
                            "qualification": flat.get("qualification") or {},
                            "search_phrase": flat.get("search_phrase") or "",
                            "requested_city": flat.get("requested_city") or "",
                            "geo_note": flat.get("geo_note") or "",
                            "online_hits": flat.get("online_hits") or 0,
                            "stamp_hint": stamp_hint,
                            "founded_at": flat.get("founded_at") or "",
                            "revenue": flat.get("revenue"),
                            "profit": flat.get("profit"),
                            "expense": flat.get("expense"),
                            "assets": flat.get("assets"),
                            "finance_year": flat.get("finance_year"),
                            "finance_source": flat.get("finance_source"),
                            "card_audit": flat.get("card_audit") or {},
                        },
                        ensure_ascii=False,
                    ),
                },
            )
            party.update(flat)
            party["stamp"] = stamp
            party["score"] = score
            party["stamp_hint"] = stamp_hint
            # Always keep audited cards in the result set (fix/warn, never drop).
            if len(verified) < target_count and str(party.get("inn") or "").strip():
                if str(party.get("stamp") or "") == "стоп" and party.get("card_audit"):
                    party["stamp"] = "осторожно"
                    party["stamp_hint"] = (
                        party.get("stamp_hint")
                        or "LLM-аудит: карточку оставили для ручной сверки"
                    )
                if str(party.get("stamp") or "") != "стоп":
                    verified.append(party)
                else:
                    dropped += 1
            await asyncio.sleep(0.08)

        def company_card(c: dict[str, Any]) -> dict[str, Any]:
            year = c.get("finance_year")
            raw_presence = c.get("presence") or {}
            presence = dict(raw_presence) if isinstance(raw_presence, dict) else {}
            audit = c.get("card_audit") if isinstance(c.get("card_audit"), dict) else {}
            contacts_untrusted = audit.get("contacts_ok") is False
            object_phone_sources = [
                src
                for src in (presence.get("phone_sources") or c.get("phone_sources") or [])
                if isinstance(src, dict)
                and "сайт объекта" in str(src.get("source") or "").lower()
            ]
            if contacts_untrusted:
                for key in (
                    "site",
                    "phone",
                    "email",
                    "vk_company",
                    "vk_group",
                    "telegram",
                    "whatsapp",
                    "max",
                    "web_lpr",
                ):
                    item = presence.get(key)
                    if not isinstance(item, dict):
                        continue
                    status = str(item.get("status") or "").lower()
                    if status == "контакт объекта" and key in {"site", "phone"}:
                        continue
                    if key == "phone" and object_phone_sources:
                        continue
                    presence[key] = {
                        "status": "перепроверить",
                        "value": "",
                        "hint": "финальный аудит не подтвердил этот контакт",
                    }
                presence["phone_sources"] = object_phone_sources
            phones_out = c.get("phones") or []
            emails_out = c.get("emails") or []
            sites_out = c.get("sites") or []
            if contacts_untrusted:
                phone_item = presence.get("phone") if isinstance(presence.get("phone"), dict) else {}
                site_item = presence.get("site") if isinstance(presence.get("site"), dict) else {}
                phones_out = [phone_item.get("value")] if phone_item.get("value") else []
                sites_out = [site_item.get("value")] if site_item.get("value") else []
                emails_out = []
            return {
                "inn": c.get("inn"),
                "name": c.get("name"),
                "okved": c.get("okved"),
                "address": c.get("address"),
                "status": c.get("status"),
                "management": c.get("management"),
                "management_post": c.get("management_post"),
                "management_label": c.get("management_label") or c.get("management") or "нет",
                "founders": c.get("founders") or [],
                "founders_detail": c.get("founders_detail") or [],
                "managers": c.get("managers") or [],
                "employee_count": c.get("employee_count"),
                "phones": c.get("phones") or [],
                "phone_sources": (presence.get("phone_sources") if isinstance(presence, dict) else None)
                or c.get("phone_sources")
                or [],
                "emails": emails_out,
                "sites": sites_out,
                "people_contacts": c.get("people_contacts") or [],
                "contact_routes": c.get("contact_routes") or [],
                "presence": presence,
                "checks": (presence.get("checks") if isinstance(presence, dict) else None) or [],
                "founded_at": c.get("founded_at") or "",
                "revenue": c.get("revenue"),
                "profit": c.get("profit"),
                "expense": c.get("expense"),
                "assets": c.get("assets"),
                "finance_year": year,
                "finance_source": c.get("finance_source"),
                "revenue_text": format_money_rub(c.get("revenue")),
                "profit_text": format_money_rub(c.get("profit")),
                "expense_text": format_money_rub(c.get("expense")),
                "assets_text": format_money_rub(c.get("assets")),
                "stamp": c.get("stamp"),
                "score": c.get("score"),
                "stamp_hint": c.get("stamp_hint") or "",
                "stamp_label": stamp_label(str(c.get("stamp") or ""), int(c.get("score") or 0)),
                "idea": c.get("idea"),
                "ogrn": c.get("ogrn"),
                "found_via": c.get("found_via") or "",
                "search_phrase": c.get("search_phrase") or "",
                "requested_city": c.get("requested_city") or "",
                "geo_note": c.get("geo_note") or "",
                "photos": c.get("photos") or [],
                "kp": c.get("kp") or {},
                "kp_status": c.get("kp_status") or "отложено",
                "object": c.get("object") or {},
                "object_address": c.get("object_address") or "",
                "owner_candidates": c.get("owner_candidates") or [],
                "lighting": lighting_score(c),
                "qualification": c.get("qualification") or {},
                "card_audit": audit,
            }

        payload = {
            "hunt_id": hunt_id,
            "already": already,
            "skipped": skipped,
            "dropped": dropped,
            "errors": errors,
            "queries": jobs,
            "companies": [company_card(c) for c in verified[:target_count]],
        }
        await db.finish_hunt(database, hunt_id, "done", payload)
        return payload
    except Exception:
        await db.finish_hunt(database, hunt_id, "error")
        raise
    finally:
        await dadata.aclose()
        await fns.aclose()
        await llm.aclose()
