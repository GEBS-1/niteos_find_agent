"""Object-first hunt: buildings/POIs before companies."""
from __future__ import annotations

import logging
import re
import json
import html as html_lib
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse

import httpx

from app.contacts import CITY_SLUG

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

# Words that usually mean a real place, not a holding / bank / media.
_OBJECTISH = (
    "склад",
    "терминал",
    "логист",
    "завод",
    "цех",
    "производ",
    "магазин",
    "торгов",
    "тц",
    "трц",
    "прачеч",
    "химчист",
    "азс",
    "заправк",
    "стадион",
    "спорт",
    "бассейн",
    "парковк",
    "офис",
    "бизнес",
    "гостиниц",
    "отел",
    "школ",
    "больниц",
    "поликлин",
    "жк ",
    "жил",
)

# The building itself (mall / BC), not a tenant sitting inside it.
_BUILDING_GRADE = (
    "торговый центр",
    "торгово-развлекательный",
    "трц",
    "тц ",
    " тц",
    "трк",
    "бизнес-центр",
    "бизнес центр",
    "бц ",
    " бц",
    "складской комплекс",
    "складск",
    "логистический комплекс",
    "логистическ",
    "логистич",
    "терминал",
    "жилой комплекс",
    "спорткомплекс",
    "спортивный комплекс",
    "стадион",
    "арена",
    "дворец спорта",
    "бассейн",
)

_SPORTS_GRADE = (
    "стадион",
    "арена",
    "спорткомплекс",
    "спортивный комплекс",
    "дворец спорта",
    "бассейн",
    "физкультур",
)

# Schools / hospitals — the building IS the institution (no separate «УК»).
_SCHOOL_GRADE = (
    "школ",
    "лицей",
    "гимнази",
    "мбоу",
    "маоу",
    "сош",
    "колледж",
    "техникум",
    "детский сад",
    "доу ",
)
_INSTITUTION_GRADE = _SCHOOL_GRADE + (
    "больниц",
    "поликлин",
    "медцентр",
    "музей",
    "дворец культуры",
    "дк ",
)


def is_school_building_title(title: str) -> bool:
    t = (title or "").strip().lower().replace("ё", "е")
    return bool(t) and any(w in t for w in _SCHOOL_GRADE)


def is_sports_building_title(title: str) -> bool:
    t = (title or "").strip().lower().replace("ё", "е")
    return bool(t) and any(w in t for w in _SPORTS_GRADE)


def is_institution_building_title(title: str) -> bool:
    t = (title or "").strip().lower().replace("ё", "е")
    return bool(t) and any(w in t for w in _INSTITUTION_GRADE)


def school_number(text: str) -> str:
    m = re.search(
        r"(?:№|n|номер)\s*(\d{1,4})\b|\b(\d{1,4})\s*(?:школ|сош|лицей|гимнази)",
        (text or "").lower().replace("ё", "е"),
        flags=re.I,
    )
    if not m:
        return ""
    return m.group(1) or m.group(2) or ""

_TENANT_WORDS = (
    "гостиниц",
    "отел",
    "хостел",
    "магазин",
    "супермаркет",
    "ресторан",
    "кафе",
    "бар ",
    "кинотеатр",
    "аптек",
    "салон",
    "клиник",
    "банк",
    "офис ",
)

_HOST_WORDS = (
    "тц",
    "трц",
    "трк",
    "торговый центр",
    "торгово-развлекательн",
    "бизнес-центр",
    "бизнес центр",
    "бц",
    "молл",
    "mall",
)


def is_tenant_inside_host(title: str) -> bool:
    """True for «Гостиница в ТРЦ Южный», «Магазин в ТЦ …» — not the building."""
    t = (title or "").strip().lower().replace("ё", "е")
    if not t:
        return False
    # Explicit "X в/при ТЦ|ТРЦ|…"
    if re.search(
        r"(гостиниц|отел|хостел|магазин|ресторан|кафе|бар|кино|аптек|салон|"
        r"клиник|банк|супермаркет)\w*\s+(в|при|внутри)\s+",
        t,
    ) and any(h in t for h in _HOST_WORDS):
        return True
    # «ТРЦ Южный (Магазин Эдельвейс)» — host label + tenant in parentheses
    if re.search(
        r"\((?:магазин|ресторан|кафе|гостиниц|отел|аптек|салон|кино|банк)[^)]*\)",
        t,
    ) and any(h in t for h in _HOST_WORDS):
        return True
    # Starts as pure building label — not a tenant
    if any(t.startswith(b.strip()) or f" {b.strip()} " in f" {t} " for b in (
        "тц",
        "трц",
        "трк",
        "торговый центр",
        "бизнес-центр",
        "бизнес центр",
    )):
        # Still reject if a tenant word sits after host prefix
        if any(w in t for w in _TENANT_WORDS) and "(" in t:
            return True
        return False
    has_tenant = any(w in t for w in _TENANT_WORDS)
    has_host = any(h in t for h in _HOST_WORDS)
    return bool(has_tenant and has_host)


def is_building_grade_title(title: str, query: str = "") -> bool:
    """Named mall / BC / complex / school — the thing we sell light to."""
    t = (title or "").strip().lower().replace("ё", "е")
    if not t or is_tenant_inside_host(title):
        return False
    if is_generic_object_title(title, query):
        return False
    if any(b in t for b in _BUILDING_GRADE):
        return True
    if is_institution_building_title(title):
        return True
    # Short branded mall names: «ТЦ Мега», «Южный», «Порт» with mall query
    q = (query or "").lower().replace("ё", "е")
    mallish_q = any(
        w in q
        for w in (
            "торгов",
            "тц",
            "трц",
            "трк",
            "бизнес центр",
            "бизнес-центр",
            "жил",
            "стадион",
            "арена",
            "спорт",
            "бассейн",
        )
    )
    warehouse_q = any(w in q for w in ("склад", "логист", "терминал"))
    if mallish_q and re.search(r"\b(тц|трц|трк|бц)\b", t):
        return True
    # Named warehouse / logistics site (not bare «склад»)
    if warehouse_q and any(w in t for w in ("склад", "логист", "терминал")) and len(t) >= 8:
        return True
    # One-token / hyphen brand under mall query: «Мега», «Парк-Хаус» — not «Мега Крепеж»
    parts = [p for p in re.split(r"\s+", t) if p]
    if mallish_q and not t.startswith("строительств") and "." not in t:
        if len(parts) == 1 and 2 <= len(t) <= 32:
            return True
        if len(parts) == 2 and "-" in t and not any(w in t for w in _TENANT_WORDS):
            return True
    return False


def _street_tokens(address: str) -> set[str]:
    """Extract comparable street/house tokens from OSM or legal addresses."""
    a = (address or "").lower().replace("ё", "е")
    if not a:
        return set()
    out: set[str] = set()
    for m in re.finditer(
        r"(?:ул\.?|улица|пр\.?|проспект|пер\.?|переулок|б-р|бульвар|ш\.?|шоссе|"
        r"наб\.?|набережная|пл\.?|площадь)\s*([a-zа-я0-9\-\s]{3,40})",
        a,
        flags=re.I,
    ):
        name = re.sub(r"\s+", " ", m.group(1)).strip(" ,.")
        for part in re.findall(r"[а-яa-z0-9]{3,}", name):
            out.add(part)
    for m in re.finditer(r"(?:д\.?|дом)\s*(\d+[а-яa-z]?)", a, flags=re.I):
        out.add(f"д{m.group(1).lower()}")
    for m in re.finditer(
        r"(\d+[\/\dа-яa-z]*)\s*,\s*(?:пр\.?|проспект|ул\.?|улица)", a, flags=re.I
    ):
        out.add(f"д{m.group(1).lower()}")
    return out


def _city_slug(city: str) -> str:
    city = (city or "").strip().lower()
    if city in CITY_SLUG:
        return CITY_SLUG[city]
    for key, slug in CITY_SLUG.items():
        if key in city or city in key:
            return slug
    return ""


# Minimum confidence to keep a legal entity attached to a building.
MIN_RELATION_CONFIDENCE = 50
# Photos only after a stronger link (avoid random facade shots).
MIN_PHOTO_RELATION_CONFIDENCE = 60


def accept_building_candidate(
    *,
    title: str,
    address: str,
    query: str,
    sphere: str = "",
) -> dict[str, Any]:
    """Hard gate before any DaData / contacts: only real buildings proceed."""
    title = (title or "").strip()
    address = (address or "").strip()
    if not title:
        return {"ok": False, "reason": "пустое название здания", "rec": None}
    if title.lower().startswith("строительств"):
        return {"ok": False, "reason": "стройка, не готовый объект", "rec": None}
    if is_tenant_inside_host(title):
        return {
            "ok": False,
            "reason": "арендатор внутри корпуса — нужен сам объект",
            "rec": None,
        }
    if is_generic_object_title(title, query):
        return {"ok": False, "reason": "слишком общее название", "rec": None}
    if not address:
        return {"ok": False, "reason": "нет адреса здания", "rec": None}
    rec = recommend_object(
        title=title, address=address, query=query, sphere=sphere
    )
    if not rec.get("ok"):
        return {
            "ok": False,
            "reason": str(rec.get("reason") or "объект не подошёл под запрос"),
            "rec": rec,
        }
    q = (query or "").lower().replace("ё", "е")
    # «склад» / shops are NOT mall-grade — don't force ТЦ/БЦ naming
    mallish = any(
        w in q
        for w in (
            "торгов",
            "тц",
            "трц",
            "трк",
            "бизнес центр",
            "бизнес-центр",
            "бц",
            "жил",
        )
    )
    warehouseish = sphere == "warehouse" or any(
        w in q for w in ("склад", "логист", "терминал")
    )
    shopish = sphere == "shops" or any(
        w in q for w in ("магазин", "пятёроч", "пятероч", "магнит", "ритейл")
    )
    azsish = sphere == "azs" or any(w in q for w in ("азс", "заправк", "автозаправ"))
    if sphere == "commercial" or mallish:
        if not is_building_grade_title(title, query):
            return {
                "ok": False,
                "reason": "нужен корпус (ТЦ/ТРЦ/БЦ/комплекс), не точка внутри",
                "rec": rec,
            }
    if warehouseish:
        low_t = title.lower().replace("ё", "е")
        looks_wh = any(
            w in low_t
            for w in ("склад", "логист", "терминал", "warehouse", "depot")
        )
        if not looks_wh and not streetish_address(address):
            return {
                "ok": False,
                "reason": "для склада нужен склад/логистика в названии или уличный адрес",
                "rec": rec,
            }
        # Accept named warehouses even without perfect street parse from OSM
        return {"ok": True, "reason": "склад/логистика принят", "rec": rec}
    if shopish:
        # Small retail POIs often lack «ул.» in OSM — allow if title isn't empty type
        if is_generic_object_title(title, query) and not streetish_address(address):
            return {
                "ok": False,
                "reason": "слишком общее название магазина",
                "rec": rec,
            }
        return {"ok": True, "reason": "торговая точка принята", "rec": rec}
    if azsish:
        low_t = title.lower().replace("ё", "е")
        looks = any(w in low_t for w in ("азс", "заправ", "татнефть", "лукойл", "газпром", "shell", "роснефть"))
        if not looks and not streetish_address(address):
            return {
                "ok": False,
                "reason": "для АЗС нужно название/бренд или уличный адрес",
                "rec": rec,
            }
        return {"ok": True, "reason": "АЗС принята", "rec": rec}
    if not streetish_address(address) and not is_building_grade_title(title, query):
        return {
            "ok": False,
            "reason": "нет уличного адреса и слабый тип здания",
            "rec": rec,
        }
    return {"ok": True, "reason": "здание принято к поиску собственника", "rec": rec}


def relation_accepted(rel: dict[str, Any] | None, *, min_score: int = MIN_RELATION_CONFIDENCE) -> bool:
    """True only if юрлицо plausibly belongs to this building."""
    if not isinstance(rel, dict):
        return False
    if str(rel.get("status") or "") == "связь не подтверждена":
        return False
    try:
        conf = int(rel.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0
    return conf >= min_score


def building_dedupe_key(title: str, address: str = "") -> str:
    t = re.sub(r"\s+", " ", (title or "").strip().lower().replace("ё", "е"))
    a = re.sub(r"\s+", " ", (address or "").strip().lower().replace("ё", "е"))
    # Keep street-ish tail so same mall name in two cities stays distinct
    a_tail = ",".join(p.strip() for p in a.split(",")[-3:] if p.strip())
    return f"{t}|{a_tail}"


def recommend_object(
    *,
    title: str,
    address: str,
    query: str,
    sphere: str = "",
) -> dict[str, Any]:
    """Heuristic recommend: does this look like the requested object type?"""
    if is_tenant_inside_host(title):
        return {
            "ok": False,
            "score": 10,
            "reason": "арендатор внутри ТЦ/ТРЦ — нужен сам корпус, не точка внутри",
            "status": "сомнительно",
        }
    blob = f"{title} {address}".lower()
    q = (query or "").lower().strip()
    reasons: list[str] = []
    score = 40
    if address.strip():
        score += 15
        reasons.append("есть адрес объекта")
    else:
        reasons.append("нет адреса — слабо")
    if q and q in blob:
        score += 25
        reasons.append(f"в названии/адресе есть «{query}»")
    elif any(w in blob for w in _OBJECTISH if len(w) >= 4):
        score += 12
        reasons.append("похож на объектный тип")
    if is_building_grade_title(title, query):
        score += 20
        if is_school_building_title(title):
            reasons.append("похоже на здание школы/лицея")
        else:
            reasons.append("похоже на само здание (ТЦ/БЦ/комплекс)")
    elif sphere == "commercial" and any(
        w in q for w in ("торгов", "тц", "трц", "бизнес")
    ):
        score -= 20
        reasons.append("для коммерции нужен корпус ТЦ/БЦ, не произвольная точка")
    schoolish_q = any(
        w in q for w in ("школ", "лицей", "гимнази", "мбоу", "сош", "детский сад")
    )
    if (sphere == "social" or schoolish_q) and is_institution_building_title(title):
        score += 15
        reasons.append("социальный объект под запрос")
    if sphere and sphere in {
        "warehouse",
        "industry",
        "shops",
        "azs",
        "laundry",
        "commercial",
        "sports",
        "street",
        "housing",
        "social",
        "office",
    }:
        score += 5
    ok = score >= 55 and bool(address.strip())
    if sphere == "commercial" and any(w in q for w in ("торгов", "тц", "трц")):
        ok = ok and is_building_grade_title(title, query)
    if (sphere == "social" or schoolish_q) and not is_institution_building_title(title):
        # Reject malls / random shops when hunting schools
        if any(w in (title or "").lower() for w in ("тц", "трц", "мега", "торгов")):
            ok = False
            reasons.append("коммерческий корпус при поиске соцобъекта")
    return {
        "ok": ok,
        "score": min(max(score, 0), 99),
        "reason": "; ".join(reasons) if reasons else "мало признаков объекта",
        "status": "подходит" if ok else "сомнительно",
    }


def _uniq(items: list[str], limit: int = 20) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
        if len(out) >= limit:
            break
    return out


_BAD_IMAGE_HOST_PARTS = (
    "bing.",
    "google.",
    "gstatic.",
    "mc.yandex",
    "vk.com/images",
    "ytimg.com",
    "youtube.com",
    "selstorage.",
    "s3.",
    "lordbokep",
    "porn",
    "porno",
    "xxx",
    "sex",
    "casino",
    "bet",
    "impawards",
    "cinematerial",
    "filmelier",
    "wikia.nocookie",
    "movieposter",
    "posterwire",
)

_BAD_IMAGE_PATH_PARTS = (
    "default-share",
    "favicon",
    "sprite",
    "icon",
    "1x1",
    "pixel",
    "logo",
    "counter",
    "watch/",
    "/map/",
    "static-map",
    "placeholder",
    "blank.",
    "poster",
    "cropped-android",
    "-32x32",
    "-192x192",
    "-180x180",
    "-270x270",
)


def _clean_image_url(raw: str) -> str:
    url = html_lib.unescape(str(raw or "")).replace("\\/", "/").strip()
    # Never unicode_escape — it corrupts real image URLs.
    url = url.split()[0].rstrip("\",';>'\\")
    return unquote(url)


def _normalize_yandex_altay_url(url: str) -> str:
    """Yandex Maps templates often end with /%s — browsers get 400/404. Force /orig."""
    clean = _clean_image_url(url)
    m = re.match(
        r"(https://avatars\.mds\.yandex\.net/get-altay/\d+/[a-f0-9]+)(?:/(.*))?$",
        clean,
        flags=re.I,
    )
    if not m:
        return clean
    base, suffix = m.group(1), (m.group(2) or "").strip()
    bad = (
        not suffix
        or suffix in {"%", "%s", "{s}", "{size}", "$1"}
        or suffix.startswith("%")
        or "{" in suffix
    )
    if bad:
        return f"{base}/orig"
    # Keep first size segment only (orig / XXL / …)
    size = suffix.split("/")[0].split("?")[0]
    if not size or size in {"%", "%s"}:
        return f"{base}/orig"
    return f"{base}/{size}"


def object_photo_ok(url: str) -> bool:
    """Accept only plausible real object photos, not service defaults or trackers."""
    clean = _normalize_yandex_altay_url(url) if "get-altay" in (url or "").lower() else _clean_image_url(url)
    low = clean.lower()
    if not low.startswith(("http://", "https://")):
        return False
    # Broken Yandex size templates
    if re.search(r"/get-altay/\d+/[a-f0-9]+/%s?$", low) or low.endswith("/get-altay/") or low.endswith("/%"):
        return False
    try:
        parsed = urlparse(clean)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if not host:
        return False
    # Yandex Maps org photos are valid object evidence.
    yandex_photo_ok = any(
        x in host
        for x in (
            "avatars.mds.yandex.net",
            "yandex-images",
            "img.yandex",
            "images.yandex",
        )
    )
    if any(part in host for part in _BAD_IMAGE_HOST_PARTS) and not yandex_photo_ok:
        return False
    if any(part in low for part in _BAD_IMAGE_PATH_PARTS):
        return False
    if path.endswith((".svg", ".gif", ".ico")):
        return False
    if yandex_photo_ok:
        # Require a real size segment (orig/XXL/…) — not a template stub
        if "get-altay" in low:
            parts = [p for p in path.split("/") if p]
            if len(parts) < 4:
                return False
            size = parts[-1]
            if size in {"%", "%s"} or size.startswith("%") or "{" in size:
                return False
        return True
    return any(
        marker in low
        for marker in (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            "/photo",
            "/image",
            "/upload",
            "/uploads",
            "/content/",
            "/media/",
        )
    )


def _photo_search_queries(obj: dict[str, Any]) -> list[str]:
    title = str(obj.get("title") or "").strip()
    city = str(obj.get("city") or "").strip()
    address = str(obj.get("address") or "").strip()
    short_address = ", ".join(x.strip() for x in address.split(",")[:3] if x.strip())
    bases: list[str] = []
    if title and city:
        bases.append(f"{title} {city}")
    if title and short_address:
        bases.append(f"{title} {short_address}")
    if title:
        bases.append(title)
    if short_address:
        bases.append(short_address)

    out: list[str] = []
    school = is_school_building_title(title)
    sports = is_sports_building_title(title)
    for base in _uniq(bases, 4):
        low = base.lower()
        if len(base) < 5 or low in {"тц", "трц", "магазин", "торговый центр", "школа", "стадион"}:
            continue
        if sports:
            # Exterior / night façade — for architectural lighting projection
            out.append(f"{base} фасад снаружи")
            out.append(f"{base} ночной вид")
            out.append(f"{base} здание внешний вид")
            out.append(f"{base} стадион фото")
        elif school:
            out.append(f"{base} фасад")
            out.append(f"{base} здание фото")
            out.append(f"{base} фото")
        else:
            out.append(f"{base} фасад фото")
            out.append(f"{base} здание снаружи")
            out.append(f"{base} ночной фасад")
    if school and title and city:
        num = school_number(title)
        if num:
            out.insert(0, f"школа №{num} {city} фасад")
            out.insert(1, f"школа {num} {city} здание")
    if sports and title and city:
        out.insert(0, f'"{title}" {city} фасад снаружи')
        out.insert(1, f'"{title}" {city} exterior')
        out.insert(2, f"{title} {city} stadium facade")
        out.insert(3, f'site:commons.wikimedia.org {title}')
    return _uniq(out, 10)


_BAD_PHOTO_HINTS = (
    # interiors / food / retail — useless for façade lighting КП
    "interior",
    "интерьер",
    "внутри",
    "indoor",
    "трибун",
    "locker",
    "раздевал",
    "logo",
    "логотип",
    "avatar",
    "icon",
    "sprite",
    "map_",
    "schema",
    "план ",
    "cafe",
    "café",
    "кофе",
    "coffee",
    "ресторан",
    "restaurant",
    "меню",
    "menu",
    "еда",
    "food",
    "dessert",
    "десерт",
    "торт",
    "cake",
    "кухн",
    "kitchen",
    "бар ",
    "bar/",
    "/bar.",
    "lounge",
    "лобби",
    "lobby",
    "фудкорт",
    "foodcourt",
    "food-court",
    "столов",
    "банкет",
    "buffet",
    "пицц",
    "pizza",
    "суши",
    "sushi",
    "магазин",
    "shop",
    "store",
    "витрин",
    "plate",
    "тарел",
    "натюрморт",
    "selfie",
    "портрет",
    "portrait",
)

_EXTERIOR_HINTS = (
    "фасад",
    "facade",
    "façade",
    "exterior",
    "снаружи",
    "outdoor",
    "outside",
    "building",
    "здание",
    "aerial",
    "drone",
    "night",
    "ночн",
    "stadium",
    "стадион",
    "арена",
    "arena",
    "wikimedia",
    "wikipedia",
    "get-altay",
)


def _photo_looks_exterior(url: str) -> bool:
    """Reject obvious interior/food/retail shots by URL path/host hints."""
    low = (url or "").lower()
    if any(h in low for h in _BAD_PHOTO_HINTS):
        return False
    # Wikimedia building photos are almost always exterior architecture shots
    if "upload.wikimedia.org" in low or "wikipedia.org" in low:
        return True
    # Yandex Maps org gallery — keep; interiors filtered later by context/rank
    if "get-altay" in low:
        return True
    # Bing/site hits: prefer paths that smell like façade
    if any(h in low for h in _EXTERIOR_HINTS):
        return True
    # Unknown CDN without exterior signal — too risky (cafés, desserts)
    return False


def _html_photo_context_ok(html: str, url: str, *, window: int = 280) -> bool:
    """Drop gallery items whose nearby HTML mentions food/interior."""
    if not html or not url:
        return True
    needle = url[:80]
    idx = html.find(needle)
    if idx < 0:
        # try without size suffix
        base = re.sub(r"/(orig|xxl|xl|l|m|s|%s?)$", "", url, flags=re.I)
        idx = html.find(base[:70]) if base else -1
    if idx < 0:
        return True
    chunk = html[max(0, idx - window) : idx + window].lower()
    return not any(h in chunk for h in _BAD_PHOTO_HINTS)


async def _bing_image_urls(client: httpx.AsyncClient, query: str, limit: int = 8) -> list[str]:
    if not query.strip():
        return []
    url = f"https://www.bing.com/images/search?q={quote_plus(query)}&form=HDRSC2"
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=18.0)
    except Exception as exc:
        log.info("image search failed %s: %s", query, exc)
        return []
    if resp.status_code >= 400:
        return []
    html = resp.text or ""
    found: list[str] = []
    patterns = (
        r'"murl"\s*:\s*"([^"]{10,800})"',
        r'murl&quot;\s*:\s*&quot;([^&]{10,800})&quot;',
    )
    for pattern in patterns:
        for m in re.finditer(pattern, html, flags=re.I):
            img = _clean_image_url(m.group(1))
            if object_photo_ok(img):
                found.append(img)
                if len(found) >= limit:
                    return _uniq(found, limit)
    return _uniq(found, limit)


async def _yandex_image_urls(
    client: httpx.AsyncClient, query: str, limit: int = 8
) -> list[str]:
    """Free Yandex Images HTML scrape — no LLM. Prefer original img_href / img_url."""
    from urllib.parse import unquote

    if not query.strip():
        return []
    url = f"https://yandex.ru/images/search?text={quote_plus(query)}"
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=18.0)
    except Exception as exc:
        log.info("yandex images failed %s: %s", query, exc)
        return []
    if resp.status_code >= 400:
        return []
    html = resp.text or ""
    found: list[str] = []
    patterns = (
        r'img_href&quot;:&quot;(https?://[^&]{10,800})&quot;',
        r'"img_href"\s*:\s*"(https?://[^"]{10,800})"',
        r'img_url=(https?%3A%2F%2F[^&\"\'\s]{10,800})',
        r'"origUrl"\s*:\s*"(https?://[^"]{10,800})"',
        r'&quot;origUrl&quot;:&quot;(https?://[^&]{10,800})&quot;',
        r'(//avatars\.mds\.yandex\.net/i\?id=[^\"\'&\s]+)',
    )
    for pattern in patterns:
        for m in re.finditer(pattern, html, flags=re.I):
            raw = m.group(1)
            if "%3A" in raw or "%2F" in raw:
                raw = unquote(raw)
            if raw.startswith("//"):
                raw = "https:" + raw
            img = _clean_image_url(raw)
            if not img:
                continue
            # Skip yastatic UI chrome
            if "yastatic.net" in img.lower():
                continue
            if object_photo_ok(img) or "avatars.mds.yandex.net" in img.lower():
                found.append(img)
                if len(found) >= limit * 2:
                    break
        if len(found) >= limit:
            break
    return _uniq(found, limit)


def is_generic_object_title(title: str, query: str = "") -> bool:
    """True when title is just the search phrase / empty type label."""
    t = (title or "").strip().lower().replace("ё", "е")
    q = (query or "").strip().lower().replace("ё", "е")
    if not t or len(t) < 3:
        return True
    generics = {
        "торговый центр",
        "тц",
        "трц",
        "склад",
        "магазин",
        "завод",
        "офис",
        "бизнес центр",
        "бизнес-центр",
        "прачечная",
        "азс",
        "здание",
        "объект",
        "школа",
        "больница",
        "поликлиника",
        "лицей",
        "гимназия",
    }
    if t in generics:
        return True
    if q and (t == q or t.startswith(q + " ") or q.startswith(t)):
        # "торговый центр" / "торговый центр казань"
        rest = t.replace(q, "").strip(" ,.-")
        if not rest or rest in {"казань", "москва", "россия", "г", "город"}:
            return True
    return False


def short_company_label(name: str) -> str:
    """Strip legal form noise for map/VK search."""
    text = (name or "").strip()
    text = re.sub(
        r'^(ООО|АО|ПАО|ЗАО|ИП|НАО|ОАО)\s*[«"\']?\s*',
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r'[»"\']', "", text)
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    return text[:80]


def _tokens(text: str) -> set[str]:
    text = (text or "").lower().replace("ё", "е")
    stop = {
        "ооо",
        "ао",
        "пао",
        "зао",
        "ип",
        "общество",
        "ограниченной",
        "ответственностью",
        "торговый",
        "центр",
        "тц",
        "трц",
        "бизнес",
        "компания",
    }
    return {t for t in re.findall(r"[a-zа-я0-9]{3,}", text) if t not in stop}


def object_company_relation(company: dict[str, Any], obj: dict[str, Any]) -> dict[str, Any]:
    """Conservative object-company link: never call ownership confirmed without proof."""
    company_name = str(company.get("name") or "")
    company_address = str(company.get("address") or "")
    object_title = str(obj.get("title") or "")
    object_address = str(obj.get("address") or "")
    company_tokens = _tokens(company_name)
    object_tokens = _tokens(object_title)
    overlap = sorted(company_tokens & object_tokens)
    score = 35
    reasons: list[str] = []
    name_low = company_name.lower().replace("ё", "е")
    okved = str(company.get("okved") or company.get("okved_code") or "")
    school_obj = is_school_building_title(object_title)

    if is_tenant_inside_host(object_title):
        return {
            "status": "связь не подтверждена",
            "confidence": 15,
            "role": "объект похож на арендатора внутри корпуса",
            "reason": "нужен сам ТЦ/здание, не точка внутри",
        }

    if overlap:
        score += min(30, len(overlap) * 12)
        reasons.append("название юрлица пересекается с названием объекта")
    sn_obj = school_number(object_title)
    sn_co = school_number(company_name)
    if school_obj and sn_obj and sn_co and sn_obj == sn_co:
        score += 35
        reasons.append(f"номер школы совпадает (№{sn_obj})")
    if school_obj and any(
        w in name_low
        for w in ("школ", "лицей", "гимнази", "мбоу", "маоу", "сош", "образован")
    ):
        score += 28
        reasons.append("юрлицо похоже на саму школу (МБОУ/МАОУ)")
    if school_obj and okved.startswith("85"):
        score += 18
        reasons.append("ОКВЭД образования (85)")
    if school_obj and any(
        w in name_low
        for w in ("торгов", "мега", "ритейл", "гипермаркет", "трц", "тц ")
    ):
        score -= 45
        reasons.append("коммерция не подходит как оператор школы")
    sports_obj = any(
        w in object_title.lower().replace("ё", "е")
        for w in ("стадион", "спорт", "арена", "бассейн", "дворец спорта")
    )
    warehouse_obj = any(
        w in object_title.lower().replace("ё", "е")
        for w in ("склад", "логист", "терминал")
    )
    quoted = ""
    qm = re.search(r"[«\"„]([^»\"“]{3,60})[»\"“]", object_title or "")
    if qm:
        quoted = qm.group(1).strip().lower().replace("ё", "е")
    if sports_obj and any(
        w in name_low
        for w in ("стадион", "спорт", "арена", "муп", "мбу", "дирекция", "физкультур", "бассейн")
    ):
        score += 30
        reasons.append("юрлицо похоже на оператора спортсооружения")
    if sports_obj and (
        okved.startswith(("93", "84.")) or "93." in okved or okved.startswith("85.41")
    ):
        score += 16
        reasons.append("ОКВЭД спорта/муниципального управления")
    if warehouse_obj and any(
        w in name_low for w in ("склад", "логист", "терминал", "девелоп", "управл", "недвижим")
    ):
        score += 28
        reasons.append("юрлицо похоже на склад/логистику/УК")
    if warehouse_obj and okved.startswith(("52.10", "52.2", "68.", "41.", "46.")):
        score += 12
        reasons.append("ОКВЭД склада/логистики/недвижимости")
    if quoted and len(quoted) >= 4 and quoted in name_low:
        score += 32
        reasons.append(f"имя объекта «{quoted}» в названии юрлица")
    if object_address and company_address:
        street_obj = _street_tokens(object_address)
        street_co = _street_tokens(company_address)
        street_hit = sorted(street_obj & street_co)
        if street_hit:
            score += min(28, 10 + len(street_hit) * 8)
            reasons.append(f"улица/дом совпадают ({', '.join(street_hit[:3])})")
        else:
            obj_parts = {
                p.strip().lower().replace("ё", "е")
                for p in object_address.split(",")
                if len(p.strip()) >= 4
            }
            comp_low = company_address.lower().replace("ё", "е")
            matched = [p for p in obj_parts if p in comp_low]
            if matched:
                score += min(18, len(matched) * 6)
                reasons.append("юридический адрес частично совпадает с адресом объекта")
        obj_low = object_address.lower().replace("ё", "е")
        co_low = company_address.lower().replace("ё", "е")
        city_pairs = (
            ("казань", ("томск", "северск", "волгоград", "брянск", "свердлов", "ирбит")),
            ("москва", ("томск", "волгоград", "казань")),
        )
        for city, aliens in city_pairs:
            if city in obj_low and city not in co_low and any(a in co_low for a in aliens):
                score -= 30
                reasons.append("город юрлица не совпадает с городом здания")
                break
    if company.get("inn"):
        score += 5
        reasons.append("найдено юрлицо с ИНН по объектному запросу")
    # Prefer UK / property management over random tenant shops (malls/BC)
    if not school_obj and any(
        w in name_low for w in ("управл", "ук ", "ук«", "ук\"", "собствен", "девелоп")
    ):
        score += 18
        reasons.append("название похоже на УК / управляющую")
    if not school_obj and okved.startswith(("68.32", "68.20", "68.3", "41.20")):
        score += 12
        reasons.append("ОКВЭД ближе к управлению/аренде недвижимости")
    if any(w in name_low for w in ("магазин", "ресторан", "гостиниц", "отел", "аптек", "банк")):
        score -= 25
        reasons.append("похоже на арендатора, не на владельца корпуса")
    if not reasons:
        reasons.append("юрлицо найдено рядом с объектным запросом, но роль не доказана")

    if score >= 75:
        status = "вероятная связь"
        role = (
            "сама школа / оператор"
            if school_obj
            else "кандидат УК / оператор; нужна сверка"
        )
    elif score >= 50:
        status = "предположительная связь"
        role = "оператор/владелец не подтверждён"
    else:
        status = "связь не подтверждена"
        role = "нужно искать управляющего или собственника отдельно"

    return {
        "status": status,
        "confidence": min(max(score, 0), 99),
        "role": role,
        "reason": "; ".join(reasons),
    }


def _parse_2gis_cards(html: str, base_city: str) -> list[dict[str, Any]]:
    """Best-effort parse of 2GIS search HTML for firm cards."""
    out: list[dict[str, Any]] = []
    # Absolute firm links
    for m in re.finditer(
        r'href="(https://2gis\.ru/[^"]+/firm/[^"?#]+)"[^>]*>([^<]{2,120})<',
        html,
        flags=re.I,
    ):
        url, title = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
        if title:
            out.append(
                {
                    "title": title,
                    "address": "",
                    "url_2gis": url,
                    "source": "2gis",
                    "city": base_city,
                }
            )
    # Relative firm links near address-like spans
    for m in re.finditer(
        r'href="(/[^"]+/firm/\d+[^"]*)"[^>]*>\s*([^<]{2,120})\s*<',
        html,
        flags=re.I,
    ):
        path, title = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
        url = "https://2gis.ru" + path
        if title:
            out.append(
                {
                    "title": title,
                    "address": "",
                    "url_2gis": url.split("?")[0],
                    "source": "2gis",
                    "city": base_city,
                }
            )
    # Try to pull address strings near firm ids from embedded JSON snippets
    for m in re.finditer(
        r'"full_name"\s*:\s*"((?:\\.|[^"\\]){2,160})".{0,400}?"address_name"\s*:\s*"((?:\\.|[^"\\]){2,200})"',
        html,
        flags=re.S,
    ):
        title = json.loads(f'"{m.group(1)}"')
        address = json.loads(f'"{m.group(2)}"')
        out.append(
            {
                "title": title,
                "address": address,
                "url_2gis": "",
                "source": "2gis",
                "city": base_city,
            }
        )
    for m in re.finditer(
        r'"name"\s*:\s*"((?:\\.|[^"\\]){2,160})".{0,300}?"address_name"\s*:\s*"((?:\\.|[^"\\]){2,200})"',
        html,
        flags=re.S,
    ):
        title = json.loads(f'"{m.group(1)}"')
        address = json.loads(f'"{m.group(2)}"')
        if any(x in title.lower() for x in ("http", "2gis", "cookie")):
            continue
        out.append(
            {
                "title": title,
                "address": address,
                "url_2gis": "",
                "source": "2gis",
                "city": base_city,
            }
        )
    # Dedupe by title+address
    dedup: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in out:
        key = f"{item.get('title','').lower()}|{item.get('address','').lower()}"
        if key in seen:
            # Prefer row with address / url
            for i, prev in enumerate(dedup):
                pkey = f"{prev.get('title','').lower()}|{prev.get('address','').lower()}"
                if pkey.split("|")[0] == key.split("|")[0]:
                    if item.get("address") and not prev.get("address"):
                        dedup[i] = item
                    elif item.get("url_2gis") and not prev.get("url_2gis"):
                        prev["url_2gis"] = item["url_2gis"]
                    break
            continue
        seen.add(key)
        dedup.append(item)
    return dedup[:30]


async def search_objects_2gis(
    client: httpx.AsyncClient,
    *,
    query: str,
    city: str,
    limit: int = 15,
) -> list[dict[str, Any]]:
    query = (query or "").strip()
    city = (city or "").strip()
    if not query:
        return []
    slug = _city_slug(city)
    q = f"{query} {city}".strip() if city else query
    if slug:
        url = f"https://2gis.ru/{slug}/search/{quote_plus(q)}"
    else:
        url = f"https://2gis.ru/search/{quote_plus(q)}"
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=18.0)
    except Exception as exc:
        log.info("2gis search failed %s: %s", q, exc)
        return []
    if resp.status_code >= 400:
        return []
    html = resp.text or ""
    # Consent / anti-bot shell has no catalog data.
    if "acceptRiskButton" in html or (len(html) < 40000 and "/firm/" not in html):
        log.info("2gis search blocked or empty shell for %s", q)
        return []
    cards = _parse_2gis_cards(html, city)
    for card in cards:
        if not card.get("url_2gis"):
            card["url_2gis"] = url
        card["maps_yandex"] = (
            f"https://yandex.ru/maps/?text={quote_plus((card.get('address') or card.get('title') or q))}"
        )
        card["maps_google"] = (
            f"https://www.google.com/maps/search/?api=1&query="
            f"{quote_plus((card.get('address') or card.get('title') or q))}"
        )
    return cards[:limit]


async def search_objects_nominatim(
    client: httpx.AsyncClient,
    *,
    query: str,
    city: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """OpenStreetMap Nominatim — addresses of named places."""
    q = " ".join(x for x in (query, city, "Россия") if x).strip()
    if not q:
        return []
    url = "https://nominatim.openstreetmap.org/search"
    try:
        resp = await client.get(
            url,
            params={
                "q": q,
                "format": "json",
                "addressdetails": 1,
                "limit": limit,
                "countrycodes": "ru",
            },
            headers={**_HEADERS, "User-Agent": "NiteosHunt/1.0 (object research)"},
            timeout=20.0,
        )
    except Exception as exc:
        log.info("nominatim failed %s: %s", q, exc)
        return []
    if resp.status_code >= 400:
        return []
    out: list[dict[str, Any]] = []
    for item in resp.json() or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        display = str(item.get("display_name") or "").strip()
        # OSM often names amenity just «АЗС» / «Магазин» — enrich from address parts
        title = name or (display.split(",")[0].strip() if display else "")
        if title and is_generic_object_title(title, query) and display:
            parts = [p.strip() for p in display.split(",") if p.strip()]
            # Prefer «АЗС, ул. …» / brand-ish second token over bare amenity label
            if len(parts) >= 2:
                title = f"{parts[0]} ({parts[1]})"
            elif len(parts) == 1:
                title = parts[0]
        addr_obj = item.get("address") if isinstance(item.get("address"), dict) else {}
        if title and is_generic_object_title(title, query) and isinstance(addr_obj, dict):
            road = str(addr_obj.get("road") or addr_obj.get("pedestrian") or "").strip()
            suburb = str(addr_obj.get("suburb") or addr_obj.get("neighbourhood") or "").strip()
            brandish = suburb or road
            if brandish:
                title = f"{name or title} ({brandish})"
        address = display or title
        lat, lon = item.get("lat"), item.get("lon")
        osm_url = ""
        if item.get("osm_type") and item.get("osm_id"):
            osm_url = f"https://www.openstreetmap.org/{item['osm_type']}/{item['osm_id']}"
        out.append(
            {
                "title": title or address,
                "address": address,
                "lat": lat,
                "lon": lon,
                "url_osm": osm_url,
                "url_2gis": "",
                "maps_yandex": (
                    f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=sat"
                    if lat and lon
                    else f"https://yandex.ru/maps/?text={quote_plus(address)}"
                ),
                "maps_google": (
                    f"https://www.google.com/maps/@{lat},{lon},18z"
                    if lat and lon
                    else f"https://www.google.com/maps/search/?api=1&query={quote_plus(address)}"
                ),
                "source": "osm",
                "city": city,
            }
        )
    return out


async def _bing_web_links(client: httpx.AsyncClient, query: str, limit: int = 12) -> list[str]:
    """Web links via Brave → DuckDuckGo → Bing."""
    if not query.strip():
        return []
    links: list[str] = []
    try:
        resp = await client.get(
            "https://search.brave.com/search",
            params={"q": query, "source": "web"},
            headers=_HEADERS,
            timeout=18.0,
        )
        html = resp.text or ""
        for m in re.finditer(r'href="(https?://[^"]+)"', html):
            href = html_lib.unescape(m.group(1))
            low = href.lower()
            if any(x in low for x in ("brave.com", "brave.cloud", "youtube.com")):
                continue
            links.append(href.split("&")[0])
            if len(links) >= limit * 2:
                break
    except Exception as exc:
        log.info("brave web failed %s: %s", query, exc)
    if len(links) >= limit:
        return _uniq(links, limit)
    try:
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=_HEADERS,
            timeout=18.0,
        )
        if resp.status_code < 400 and "anomaly" not in (resp.text or "").lower():
            html = resp.text or ""
            for raw in re.findall(r'uddg=([^&\"\']+)', html):
                href = unquote(raw)
                if href.startswith("http") and "duckduckgo." not in href.lower():
                    links.append(href.split("&")[0])
    except Exception as exc:
        log.info("ddg web failed %s: %s", query, exc)
    if len(links) >= limit:
        return _uniq(links, limit)
    url = f"https://www.bing.com/search?q={quote_plus(query)}&setlang=ru"
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=18.0)
    except Exception as exc:
        log.info("bing web failed %s: %s", query, exc)
        return _uniq(links, limit)
    if resp.status_code >= 400:
        return _uniq(links, limit)
    for m in re.finditer(r'href="(https?://[^"]+)"', resp.text or ""):
        href = html_lib.unescape(m.group(1))
        if "bing.com" in href or "microsoft.com" in href:
            continue
        links.append(href.split("&")[0])
    return _uniq(links, limit)


async def search_objects_yandex(
    client: httpx.AsyncClient,
    *,
    query: str,
    city: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find named Yandex Maps org cards only (not bare ?text= search)."""
    q = " ".join(x for x in (query, city) if x).strip()
    if not q:
        return []
    searches = [
        f"{q} site:yandex.ru/maps/org",
        f'"{query}" {city} site:yandex.ru/maps/org' if query else q,
        f"{q} яндекс карты организация",
    ]
    links: list[str] = []
    for s in searches:
        if s:
            links.extend(await _bing_web_links(client, s, limit=12))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in links:
        low = link.lower()
        if "yandex.ru/maps/org" not in low and "yandex.com/maps/org" not in low:
            continue
        if any(x in low for x in ("/routes", "/traffic", "login")):
            continue
        key = link.split("?")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        title = ""
        address = city
        raw_title = ""
        try:
            resp = await client.get(key, headers=_HEADERS, timeout=14.0)
            html = resp.text or ""
        except Exception:
            html = ""
        if html:
            tm = re.search(
                r'property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                html,
                re.I,
            )
            if not tm:
                tm = re.search(
                    r'content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
                    html,
                    re.I,
                )
            if not tm:
                tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if tm:
                raw_title = html_lib.unescape(tm.group(1))
                title = _clean_yandex_org_title(raw_title)
            am = re.search(
                r'property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
                html,
                re.I,
            )
            if not am:
                am = re.search(
                    r'content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
                    html,
                    re.I,
                )
            if am:
                cand = html_lib.unescape(am.group(1)).strip()
                if _looks_like_address(cand):
                    address = cand
            if not _looks_like_address(address):
                address = _address_from_yandex_title(raw_title or title, city) or address
        if not title or is_generic_object_title(title, query):
            m = re.search(r"/maps/org/([^/]+)/", key)
            if m:
                slug_title = unquote(m.group(1)).replace("_", " ").replace("-", " ").strip()
                if slug_title and not is_generic_object_title(slug_title, query):
                    title = _clean_yandex_org_title(slug_title)
        if not title or is_generic_object_title(title, query):
            continue
        out.append(
            {
                "title": title,
                "address": address,
                "url_2gis": "",
                "url_osm": "",
                "maps_yandex": key,
                "maps_google": (
                    "https://www.google.com/maps/search/?api=1&query="
                    + quote_plus(" ".join(x for x in (title, address or city) if x))
                ),
                "source": "yandex",
                "city": city,
            }
        )
        if len(out) >= limit:
            break
    return out


def _clean_yandex_org_title(title: str) -> str:
    """Turn 'Республика, торговый центр, Казань, ул. …' into a usable place name."""
    title = html_lib.unescape(title or "")
    title = re.split(r"\s[—\-·|]\s", title)[0].strip()
    title = re.sub(r"\s+", " ", title)
    parts = [p.strip() for p in title.split(",") if p.strip()]
    if len(parts) >= 2:
        kind = parts[1].lower()
        name = parts[0]
        if any(x in kind for x in ("торгов", "тц", "трц", "рынок", "молл", "центр")):
            if not any(x in name.lower() for x in ("тц", "трц", "торгов")):
                if "рынок" in kind:
                    return f"Рынок {name}"
                return f"ТЦ {name}"
            return name
    return title


def _looks_like_address(text: str) -> bool:
    low = (text or "").lower()
    if not low or len(low) < 8:
        return False
    if any(
        x in low
        for x in (
            "⭐",
            "рейтинг",
            "отзыв",
            "фото.",
            "посмотреть номер",
            "часы работы",
        )
    ):
        return False
    return any(
        x in low
        for x in (
            "ул.",
            "улиц",
            "просп",
            "пер.",
            "шоссе",
            "набер",
            "д.",
            "зд.",
            "дом",
            "казань",
            "москва",
            "область",
            "республик",
        )
    )


def streetish_address(text: str) -> bool:
    """True when text looks like a concrete street/building address, not just a city."""
    low = (text or "").lower().replace("ё", "е")
    if not low or len(low) < 10:
        return False
    if any(x in low for x in ("рейтинг", "отзыв", "⭐", "фото объекта")):
        return False
    has_street = any(
        x in low
        for x in (
            "ул ",
            "ул.",
            "улиц",
            "просп",
            "пр-т",
            "пер.",
            "переул",
            "шоссе",
            "набер",
            "бульвар",
            "б-р",
            "тракт",
        )
    )
    has_house = bool(re.search(r"(?:\bд\.?\s*|\bзд\.?\s*|\bдом\s*|\bстр\.?\s*)\d+", low)) or bool(
        re.search(r",\s*\d+[а-яa-z]?\b", low)
    )
    return has_street and (has_house or "помещ" in low or "оф" in low)


def _address_from_yandex_title(title: str, city: str) -> str:
    parts = [p.strip() for p in (title or "").split(",") if p.strip()]
    if len(parts) >= 3:
        tail = ", ".join(parts[2:])
        if _looks_like_address(tail):
            return tail
    return city or ""


async def search_objects(
    client: httpx.AsyncClient,
    *,
    query: str,
    cities: list[str],
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Combine open sources: Yandex first, then OSM, then 2GIS."""
    cities = [c for c in cities if c.strip()] or [""]
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    per = max(4, limit // max(len(cities), 1))
    # Extra typed queries so bare «АЗС» / «склад» still find map POIs
    qlow = (query or "").lower().replace("ё", "е")
    alt_queries = [query]
    if any(w in qlow for w in ("торгов", "тц", "трц", "трк")):
        for city in cities:
            if not city:
                continue
            alt_queries.extend(
                [
                    f"ТРЦ {city}",
                    f"ТЦ {city}",
                    f"торговый центр {city}",
                    f"мега {city}",
                ]
            )
    if any(w in qlow for w in ("азс", "заправк", "автозаправ")):
        for city in cities:
            if not city:
                continue
            alt_queries.extend(
                [
                    f"АЗС {city}",
                    f"автозаправка {city}",
                    f"Татнефть АЗС {city}",
                    f"Лукойл АЗС {city}",
                ]
            )
    if any(w in qlow for w in ("склад", "логист", "терминал")):
        for city in cities:
            if not city:
                continue
            alt_queries.extend(
                [
                    f"склад {city}",
                    f"складской комплекс {city}",
                    f"логистический комплекс {city}",
                ]
            )
    if any(w in qlow for w in ("магазин", "пятёроч", "пятероч", "магнит")):
        for city in cities:
            if not city:
                continue
            alt_queries.extend(
                [
                    f"магазин {city}",
                    f"Пятёрочка {city}",
                    f"Магнит {city}",
                ]
            )
    seen_q: set[str] = set()
    queries = []
    for q in alt_queries:
        k = (q or "").strip().lower()
        if k and k not in seen_q:
            seen_q.add(k)
            queries.append(q.strip())

    for qtry in queries:
        for city in cities:
            for fn in (search_objects_yandex, search_objects_nominatim, search_objects_2gis):
                try:
                    batch = await fn(client, query=qtry, city=city, limit=per)
                except Exception:
                    log.exception("object search failed %s %s", fn.__name__, city)
                    continue
                for item in batch:
                    title = str(item.get("title") or "")
                    address = str(item.get("address") or "")
                    # Bare amenity labels are OK if we already enriched title or have street address
                    if is_generic_object_title(title, query) and not streetish_address(address):
                        # last chance: keep if title contains brand/number after type word
                        low_t = title.lower().replace("ё", "е")
                        if not re.search(r"(азс|магазин|склад).{2,}", low_t):
                            continue
                    if is_tenant_inside_host(title):
                        continue
                    # Dedupe by normalized title (ignore duplicate OSM/Yandex copies)
                    title_key = re.sub(r"\s+", " ", title.lower().replace("ё", "е")).strip()
                    title_key = re.sub(r'[«»"\']', "", title_key)
                    if title_key in seen:
                        continue
                    seen.add(title_key)
                    found.append(item)
                    if len(found) >= limit:
                        found.sort(
                            key=lambda o: (
                                0 if is_building_grade_title(str(o.get("title") or ""), query) else 1,
                                str(o.get("title") or ""),
                            )
                        )
                        return found
    found.sort(
        key=lambda o: (
            0 if is_building_grade_title(str(o.get("title") or ""), query) else 1,
            str(o.get("title") or ""),
        )
    )
    return found


def _photo_matches_building(url: str, title: str) -> bool:
    """Drop obvious off-topic hits (movie posters, random stock, wrong wiki pages)."""
    low = (url or "").lower()
    if any(
        j in low
        for j in (
            "poster",
            "movie",
            "film",
            "robot",
            "impawards",
            "cinematerial",
            "filmelier",
            "wikia",
            "vectorstock",
            "shutterstock",
            "dreamstime",
            "freepik",
            "istock",
            "gettyimages",
            "arcade",
            "clipart",
        )
    ):
        return False
    # Yandex Maps altay photos from the org card are object photos
    if "avatars.mds.yandex.net/get-altay" in low:
        return True
    title_l = (title or "").lower().replace("ё", "е")
    tokens = [
        t
        for t in re.findall(r"[а-яa-z0-9]{4,}", title_l)
        if t
        not in {
            "стадион",
            "арена",
            "футбольн",
            "здание",
            "школа",
            "улица",
            "проспект",
        }
    ]
    # Keep distinctive tokens (казань, акбарс, mega, …)
    latin_hints = (
        "kazan",
        "arena",
        "akbars",
        "ak-bars",
        "stadium",
        "stadion",
        "yamash",
    )
    if any(h in low for h in latin_hints):
        return True
    if tokens and any(t in low for t in tokens):
        return True
    # Wikimedia: require at least one title token in path
    if "wikimedia.org" in low or "wikipedia.org" in low:
        return bool(tokens) and any(t in low for t in tokens)
    # Other CDNs: require a title token in URL — otherwise too many cafés/stock
    if tokens:
        return any(t in low for t in tokens)
    return False


def _extract_yandex_org_photos(html: str) -> list[str]:
    found: list[str] = []
    seen_ids: set[str] = set()
    for m in re.finditer(
        r"https://avatars\.mds\.yandex\.net/get-altay/(\d+)/([a-f0-9]+)(?:/[^\"'\\s<>]*)?",
        html or "",
        flags=re.I,
    ):
        album, pid = m.group(1), m.group(2)
        key = f"{album}/{pid}"
        if key in seen_ids:
            continue
        seen_ids.add(key)
        # Always use /orig — templates like /%s and tiny /S are useless
        u = f"https://avatars.mds.yandex.net/get-altay/{album}/{pid}/orig"
        if object_photo_ok(u):
            found.append(u)
    return found[:12]


async def _resolve_maps_org_url(
    client: httpx.AsyncClient, *, title: str, city: str
) -> str:
    """Best-effort Yandex /org/ URL for photo gallery."""
    if not title:
        return ""
    queries = [title]
    low = title.lower().replace("ё", "е")
    # Alias expansions only for the same named venue (not for every stadium hunt)
    if "казань арена" in low or "ак барс арена" in low or "ak bars arena" in low:
        queries.extend(["Казань Арена", "Ак Барс Арена", "Ak Bars Arena Казань"])
    elif city:
        queries.append(f"{title} {city}")
    for q in _uniq(queries, 4):
        try:
            objs = await search_objects(
                client, query=q, cities=[city] if city else [], limit=6
            )
        except Exception:
            objs = []
        title_l = title.lower().replace("ё", "е")
        for o in objs or []:
            maps = str(o.get("maps_yandex") or "")
            if "/org/" not in maps or "text=" in maps:
                continue
            ot = str(o.get("title") or "").lower().replace("ё", "е")
            if any(tok in ot for tok in ("арена", "стадион", "ак барс")) or any(
                tok in title_l for tok in re.findall(r"[а-яa-z0-9]{4,}", ot)[:4]
            ):
                return maps.split("?")[0]
        for o in objs or []:
            maps = str(o.get("maps_yandex") or "")
            if "/org/" in maps and "text=" not in maps:
                return maps.split("?")[0]

    # Fallback: scrape Yandex Maps search HTML for /org/ links
    for q in _uniq([f"{title} {city}".strip(), title, *queries], 5):
        try:
            resp = await client.get(
                f"https://yandex.ru/maps/?text={quote_plus(q)}",
                headers=_HEADERS,
                timeout=16.0,
            )
        except Exception:
            continue
        html = resp.text or ""
        for m in re.finditer(
            r"https://yandex\.(?:ru|com)/maps/org/[a-z0-9_\-]+/\d+",
            html,
            flags=re.I,
        ):
            return m.group(0)
        for m in re.finditer(r"/maps/org/([a-z0-9_\-]+)/(\d+)", html, flags=re.I):
            return f"https://yandex.ru/maps/org/{m.group(1)}/{m.group(2)}"
    return ""


def _image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Width/height from JPEG/PNG header without Pillow."""
    if not data or len(data) < 24:
        return None
    # PNG
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        w = int.from_bytes(data[16:20], "big")
        h = int.from_bytes(data[20:24], "big")
        if w > 0 and h > 0:
            return w, h
    # JPEG
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker in {0xC0, 0xC1, 0xC2}:  # SOF0/1/2
                h = int.from_bytes(data[i + 5 : i + 7], "big")
                w = int.from_bytes(data[i + 7 : i + 9], "big")
                if w > 0 and h > 0:
                    return w, h
            if marker == 0xD9:
                break
            if marker in {0xD8, 0x01} or (0xD0 <= marker <= 0xD7):
                i += 2
                continue
            if i + 3 >= len(data):
                break
            seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
            if seg_len < 2:
                break
            i += 2 + seg_len
    # WebP VP8X / VP8
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        if data[12:16] == b"VP8 " and len(data) >= 30:
            w = int.from_bytes(data[26:28], "little") & 0x3FFF
            h = int.from_bytes(data[28:30], "little") & 0x3FFF
            if w > 0 and h > 0:
                return w, h
        if data[12:16] == b"VP8X" and len(data) >= 30:
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            if w > 0 and h > 0:
                return w, h
    return None


async def _photo_is_exterior_candidate(
    client: httpx.AsyncClient, url: str
) -> bool:
    """Reject logos / tiny squares; keep wide façade-like frames."""
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=16.0)
    except Exception:
        return False
    if resp.status_code >= 400:
        return False
    data = resp.content or b""
    if len(data) < 20_000:
        return False
    dims = _image_dimensions(data[:65536] if len(data) > 65536 else data)
    if not dims:
        # Unknown format but large enough — keep cautiously
        return len(data) >= 80_000
    w, h = dims
    if max(w, h) < 500:
        return False
    ratio = w / max(h, 1)
    # Square logos / avatars
    if 0.85 <= ratio <= 1.15 and max(w, h) < 1200:
        return False
    # Prefer horizontal building shots; allow mild portrait façades
    if ratio < 0.7:
        return False
    return True


async def _wikipedia_building_photos(
    client: httpx.AsyncClient, title: str, city: str
) -> list[str]:
    """Reliable exterior shots for well-known venues via Wikipedia page image."""
    if not title:
        return []
    queries = [title]
    low = title.lower().replace("ё", "е")
    if "казань арена" in low or "ак барс арена" in low:
        queries = ["Kazan Arena", "Ак Барс Арена", "Казань Арена"]
    elif city and title:
        queries.append(f"{title} {city}")
    out: list[str] = []
    title_tokens = [
        t
        for t in re.findall(r"[а-яa-z0-9]{4,}", low)
        if t not in {"стадион", "футбольн", "здание", "школа"}
    ]

    def _page_ok(page_title: str) -> bool:
        pt = (page_title or "").lower().replace("ё", "е")
        if any(bad in pt for bad in ("втб", "vtb", "динамо", "лужники")):
            # wrong famous arenas unless asked
            if "казань" not in low and "ak bars" not in low and "kazan" not in low:
                return "втб" not in pt and "vtb" not in pt
            if "казань" in low or "kazan" in low:
                return False
        if title_tokens and any(t in pt for t in title_tokens):
            return True
        if "арена" in low or "arena" in low:
            return "арена" in pt or "arena" in pt
        return False

    for q in _uniq(queries, 4):
        for api in (
            "https://ru.wikipedia.org/w/api.php",
            "https://en.wikipedia.org/w/api.php",
        ):
            try:
                resp = await client.get(
                    api,
                    params={
                        "action": "query",
                        "format": "json",
                        "generator": "search",
                        "gsrsearch": q,
                        "gsrlimit": 5,
                        "prop": "pageimages",
                        "piprop": "original",
                    },
                    headers=_HEADERS,
                    timeout=14.0,
                )
            except Exception:
                continue
            if resp.status_code >= 400:
                continue
            pages = ((resp.json() or {}).get("query") or {}).get("pages") or {}
            for page in pages.values():
                if not isinstance(page, dict) or not _page_ok(str(page.get("title") or "")):
                    continue
                orig = (page.get("original") or {}).get("source") or ""
                if not orig.startswith("http"):
                    continue
                # Drop tracking junk; force https
                clean = orig.split("?")[0].replace("http://", "https://")
                if object_photo_ok(clean):
                    out.append(clean)
            if out:
                return _uniq(out, 2)
    return []


async def collect_object_photos(
    client: httpx.AsyncClient,
    obj: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Exterior building photos only — free maps/wiki/Yandex Images, no LLM."""
    title = str(obj.get("title") or "").strip()
    notes: list[str] = []
    if is_tenant_inside_host(title):
        notes.append("фото не ищем: название не похоже на само здание")
        return [], notes
    school = is_school_building_title(title)
    sports = is_sports_building_title(title)
    city = str(obj.get("city") or "").strip()
    addr = str(obj.get("address") or "")
    has_street = streetish_address(addr) or bool(
        re.search(
            r"\(([^)]*(?:ул|улиц|пр|проспект|пер|шоссе)[^)]*)\)",
            title,
            flags=re.I,
        )
    )
    # Generic bare «АЗС» without street/city — skip; enriched «АЗС (улица…)» OK
    if is_generic_object_title(title) and not has_street and not school and not sports:
        notes.append("фото не ищем: слишком общее название без адреса")
        return [], notes
    if not has_street and not school and not sports and not city:
        notes.append("фото не ищем: нет уличного адреса здания")
        return [], notes
    if (school or sports) and not has_street and not city:
        notes.append("фото не ищем: нет города для запроса")
        return [], notes

    maps = str(obj.get("maps_yandex") or "")
    if "/org/" not in maps or "text=" in maps or "pt=" in maps:
        resolved = await _resolve_maps_org_url(client, title=title, city=city)
        if resolved:
            maps = resolved
            obj = {**obj, "maps_yandex": maps}
            notes.append(f"карточка карт: {maps}")

    candidates: list[str] = []

    # 1) Yandex Maps cover
    if "/org/" in maps and "text=" not in maps:
        try:
            resp = await client.get(maps, headers=_HEADERS, timeout=16.0)
            html = resp.text or ""
            if "get-altay" not in html:
                for a, b in (("yandex.com", "yandex.ru"), ("yandex.ru", "yandex.com")):
                    if a in maps:
                        alt = maps.replace(a, b)
                        resp = await client.get(alt, headers=_HEADERS, timeout=16.0)
                        html = resp.text or ""
                        if "get-altay" in html:
                            maps = alt
                            break
        except Exception as exc:
            html = ""
            notes.append(f"карта недоступна: {exc}")
        yandex_photos = _extract_yandex_org_photos(html)
        cover_n = 1 if sports else 3
        candidates.extend(yandex_photos[:cover_n])
        if yandex_photos:
            notes.append(f"обложка Яндекс.Карт: {len(yandex_photos[:cover_n])}")

    # 2) Wikipedia exterior
    wiki = await _wikipedia_building_photos(client, title, city)
    for u in wiki:
        candidates.append(u)
    if wiki:
        notes.append(f"фото Wikipedia: {len(wiki)}")

    # 3) Free internet image search (Yandex Images → Bing) by title+city
    if len(candidates) < 2:
        forced: list[str] = []
        if title and city:
            forced.extend(
                [
                    f"{title} {city}",
                    f"{title} {city} фасад",
                    f"{title} {city} здание",
                ]
            )
        elif title:
            forced.append(title)
        for q in _uniq(forced + _photo_search_queries(obj), 5):
            more = await _yandex_image_urls(client, q, limit=8)
            if not more:
                more = await _bing_image_urls(client, q, limit=6)
            for u in more:
                img = (
                    _normalize_yandex_altay_url(u)
                    if "get-altay" in u.lower()
                    else _clean_image_url(u)
                )
                if not img:
                    continue
                # Soft filter: accept yandex thumbs; exterior heuristics when possible
                if "avatars.mds.yandex.net" in img.lower() or (
                    object_photo_ok(img)
                    and (_photo_looks_exterior(img) or school or sports)
                ):
                    candidates.append(img)
            if candidates:
                notes.append(f"фото из поиска: {q}")
                break

    # Probe bytes: drop logos / tiny squares / broken links
    kept: list[str] = []
    for u in _uniq(candidates, 10):
        if "avatars.mds.yandex.net" in u.lower():
            kept.append(u)
        elif await _photo_is_exterior_candidate(client, u):
            kept.append(u)
        if len(kept) >= 3:
            break

    if kept:
        notes.append(f"фото фасада снаружи: {len(kept)}")
    else:
        notes.append("фото фасада снаружи не найдено")
    return kept, notes

