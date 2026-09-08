from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from app.objects import object_photo_ok


_NON_OBJECT_OKVED_PREFIXES = (
    "64.20",  # activities of holding companies
    "70.10",  # head offices
    "70.22",  # management consulting
)

_OBJECT_OKVED_PREFIXES = (
    "47.",  # retail
    "52.",  # warehouses and logistics
    "10.",
    "11.",
    "16.",
    "17.",
    "20.",
    "22.",
    "23.",
    "24.",
    "25.",
    "27.",
    "28.",
    "29.",
    "31.",
    "35.",
    "41.",
    "42.",
    "43.",
    "68.20",
)

_HOLDING_WORDS = (
    "холдинг",
    "управляющ",
    "корпоративный центр",
    "головной офис",
)

_PUBLIC_COMPANY_WORDS = (
    "пао",
    "публичное акционерное общество",
)

_SPHERE_OBJECT_TERMS = {
    "shops": ("магазин", "торговая точка", "адреса магазинов"),
    "warehouse": ("распределительный центр", "склад", "логистический комплекс"),
    "commercial": (
        "коммерческое здание фасад",
        "фото фасада",
        "архитектурная подсветка",
        "входная группа",
    ),
    "industry": ("завод", "цех", "производственная площадка", "промышленное здание"),
    "azs": ("АЗС", "заправка", "топливный комплекс"),
    "laundry": ("прачечная", "производственная прачечная", "химчистка"),
    "sports": ("стадион", "спортивный комплекс", "фитнес центр", "бассейн"),
    "street": ("парковка", "дворовое освещение", "уличное освещение"),
    "housing": ("жилой комплекс", "управляющая компания ЖКХ", "ТСЖ"),
    "social": ("школа", "больница", "поликлиника", "дворец культуры"),
    "office": ("бизнес центр", "офисное здание", "коворкинг"),
}

_RETAIL_BRAND_HINTS = (
    "fix price",
    "фикс прайс",
    "фикспрайс",
    "пятёрочка",
    "пятерочка",
    "магнит",
    "перекрёсток",
    "перекресток",
    "лента",
    "ашан",
    "дикси",
)

_COMMERCIAL_OBJECT_WORDS = (
    "торговый центр",
    "трц",
    "тц",
    "бизнес-центр",
    "бизнес центр",
    "деловой центр",
    "гостиница",
    "отель",
    "ресторанный комплекс",
    "коммерческое здание",
    "фасад",
)


def _okved_prefix(okved: str, prefixes: tuple[str, ...]) -> bool:
    code = (okved or "").strip()
    return bool(code) and any(code.startswith(prefix) for prefix in prefixes)


def _photos(presence: dict[str, Any], party: dict[str, Any]) -> list[str]:
    direct = party.get("photos") or []
    if direct:
        return [str(x) for x in direct if x and object_photo_ok(str(x))]
    item = presence.get("photos") or {}
    value = item.get("value") if isinstance(item, dict) else []
    if isinstance(value, list):
        return [str(x) for x in value if x and object_photo_ok(str(x))]
    return []


def _map_links(presence: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("maps_2gis", "maps_yandex", "maps_google"):
        item = presence.get(key) or {}
        if isinstance(item, dict) and item.get("value"):
            out.append(str(item["value"]))
    return out


def _object_workflow(brand: str, city: str, sphere: str) -> dict[str, Any]:
    brand = (brand or "").strip()
    city = (city or "").strip()
    terms = _SPHERE_OBJECT_TERMS.get(sphere) or (
        "объект",
        "здание",
        "адрес",
    )
    base = " ".join(x for x in (brand, city) if x).strip()
    if not base:
        return {"queries": [], "routes": [], "steps": []}

    queries = [f"{base} {term}" for term in terms]
    if sphere == "shops":
        queries.append(f"{base} распределительный центр")
    if sphere == "warehouse":
        queries.append(f"{base} складской комплекс")

    first = queries[0]
    routes = [
        {
            "title": "2ГИС · объекты",
            "url": f"https://2gis.ru/search/{quote_plus(first)}",
            "hint": "найти реальные точки и фото",
        },
        {
            "title": "Яндекс.Карты · объекты",
            "url": f"https://yandex.ru/maps/?text={quote_plus(first)}",
            "hint": "сверить фасад и адрес",
        },
        {
            "title": "Google Maps · объекты",
            "url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(first)}",
            "hint": "проверить фото здания",
        },
        {
            "title": "Google · сайт и адреса",
            "url": f"https://www.google.com/search?q={quote_plus(base + ' официальный сайт адреса объектов')}",
            "hint": "найти страницу сети/адресов",
        },
    ]
    return {
        "queries": queries[:6],
        "routes": routes,
        "steps": [
            "Открыть карты и выбрать конкретную точку, РЦ, склад или здание.",
            "Проверить фото фасада, подъезды, вывеску, адрес и доступность объекта.",
            "Найти на сайте сети или в открытых источниках оператора/управляющего объектом.",
            "После подтверждения объекта считать оборудование и готовить КП под здание.",
        ],
    }


def _architecture_profile(
    *,
    name: str,
    address: str,
    sphere: str,
    photos: list[str],
    maps: list[str],
    object_confirmed: bool,
) -> dict[str, Any]:
    text = f"{name} {address}".lower()
    commercial_hint = sphere == "commercial" or any(
        word in text for word in _COMMERCIAL_OBJECT_WORDS
    )
    if not commercial_hint:
        return {}
    reasons: list[str] = []
    if photos:
        reasons.append("есть фото фасада/объекта из открытых источников")
    if maps:
        reasons.append("есть карта для сверки адреса и окружения")
    if any(word in text for word in ("торговый центр", "трц", "тц")):
        reasons.append("торговый объект с вечерним трафиком")
    if any(word in text for word in ("бизнес", "деловой", "офис")):
        reasons.append("деловой объект, где важен статус фасада")
    if any(word in text for word in ("отель", "гостиница", "ресторан")):
        reasons.append("гостевой объект, где подсветка влияет на узнаваемость")
    if not reasons:
        reasons.append("коммерческий фасад можно оценить по фото и карте")
    fit = "готовить объектное предложение" if object_confirmed else "сначала подтвердить фасад"
    return {
        "fit": fit,
        "reasons": reasons[:5],
        "proposal_angles": [
            "акцентная подсветка фасада и входной группы",
            "линейная подсветка архитектурных элементов",
            "подсветка вывески, периметра и пешеходных подходов",
            "сценарий вечернего вида с расчётом яркости и стоимости",
        ],
        "first_offer": (
            "Предложить быстрый световой аудит по фото и карте: 2-3 варианта подсветки, "
            "ориентировочная спецификация NITEOS и бюджет до выезда на объект."
        ),
    }


def _workflow_sphere(search_phrase: str, sphere: str) -> str:
    if sphere:
        return sphere
    norm = (search_phrase or "").strip().lower().replace("ё", "е")
    if any(hint.replace("ё", "е") in norm for hint in _RETAIL_BRAND_HINTS):
        return "shops"
    if any(hint.replace("ё", "е") in norm for hint in _COMMERCIAL_OBJECT_WORDS):
        return "commercial"
    return ""


def qualify_lead(party: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a legal entity is usable as an object-led NITEOS lead."""
    presence = party.get("presence") or {}
    okved = str(party.get("okved") or "")
    name = str(party.get("name") or "")
    address = str(party.get("address") or "")
    obj = party.get("object") or {}
    object_title = str(obj.get("title") or "").strip()
    object_address = str(obj.get("address") or party.get("object_address") or "").strip()
    search_phrase = str(party.get("search_phrase") or "").strip()
    requested_city = str(party.get("requested_city") or "").strip()
    sphere = _workflow_sphere(
        search_phrase,
        str(party.get("sphere") or "").strip(),
    )
    text = f"{name} {address} {object_title} {object_address}".lower()

    legal_reasons: list[str] = []
    if _okved_prefix(okved, _NON_OBJECT_OKVED_PREFIXES):
        legal_reasons.append(f"ОКВЭД {okved} похож на холдинг/управляющую компанию")
    if any(word in text for word in _HOLDING_WORDS):
        legal_reasons.append("название или адрес похожи на головное/управляющее юрлицо")
    is_public_company = any(word in text for word in _PUBLIC_COMPANY_WORDS)
    if is_public_company:
        legal_reasons.append("публичное юрлицо сети не подтверждает конкретный объект")

    has_operational_okved = _okved_prefix(okved, _OBJECT_OKVED_PREFIXES)
    photos = _photos(presence, party)
    maps = _map_links(presence)
    for key in ("url_2gis", "url_osm", "maps_yandex", "maps_google"):
        value = obj.get(key) if isinstance(obj, dict) else ""
        if value:
            maps.append(str(value))
    maps = list(dict.fromkeys(maps))
    object_hint = ((presence.get("object_hint") or {}).get("value") or "").strip()
    site = ((presence.get("site") or {}).get("value") or "").strip()
    relation = obj.get("relation") if isinstance(obj, dict) else {}
    commercial_object = sphere in {"commercial", "office", "sports", "street", "housing", "social"} or any(
        word in text for word in _COMMERCIAL_OBJECT_WORDS
    )

    non_object_legal_entity = (bool(legal_reasons) and not has_operational_okved) or (
        is_public_company and bool(search_phrase)
    )
    if non_object_legal_entity:
        object_evidence = ["конкретный объект не подтверждён"]
        object_confirmed = False
    else:
        object_evidence: list[str] = []
        if object_title:
            object_evidence.append(f"найден объект: {object_title}")
        if object_address:
            object_evidence.append(f"адрес объекта: {object_address}")
        if object_hint:
            object_evidence.append(object_hint)
        if photos:
            object_evidence.append(f"есть проверенные фото фасада/объекта: {len(photos)}")
        else:
            object_evidence.append("фото фасада не подтверждено")
        if maps:
            object_evidence.append("есть ссылки на карты")
        if isinstance(relation, dict) and relation.get("status"):
            object_evidence.append(
                f"связь с компанией: {relation.get('status')} ({relation.get('confidence', '—')}/99)"
            )
        if has_operational_okved:
            object_evidence.append(f"ОКВЭД {okved} допускает объектный сценарий")
        if site:
            object_evidence.append("есть сайт для сверки объекта")
        if commercial_object:
            object_confirmed = bool(photos and maps and (object_title or object_address or object_hint))
        else:
            object_confirmed = bool(photos or (object_hint and (site or maps) and has_operational_okved))

    if non_object_legal_entity:
        status = "не объектный лид"
        next_step = (
            "Искать конкретные магазины, склады, РЦ или здания бренда через карты, сайт сети "
            "и публичные страницы объектов; это юрлицо не брать как владельца объекта."
        )
    elif object_confirmed:
        status = "объект подтверждён"
        next_step = "Сверить фото/адрес объекта и готовить предварительное решение NITEOS."
    else:
        status = "нужна проверка объекта"
        next_step = (
            "Найти объект на картах/сайте, проверить фото фасада, адрес, оператора или владельца здания."
        )

    architecture = _architecture_profile(
        name=object_title or name,
        address=object_address or address,
        sphere=sphere,
        photos=photos,
        maps=maps,
        object_confirmed=object_confirmed,
    )

    return {
        "lead_status": status,
        "object_confirmed": object_confirmed,
        "non_object_legal_entity": non_object_legal_entity,
        "legal_reasons": legal_reasons,
        "object_evidence": object_evidence,
        "next_step": next_step,
        "architecture": architecture,
        "object_workflow": _object_workflow(
            search_phrase or name,
            requested_city,
            sphere,
        ),
    }
