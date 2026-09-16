from __future__ import annotations

import httpx

from app.config import settings
from app.providers.base import ObjectCandidate


_CITY_SLUG = {
    "казань": "kazan",
    "москва": "moscow",
    "санкт-петербург": "spb",
    "спб": "spb",
    "екатеринбург": "ekaterinburg",
    "новосибирск": "novosibirsk",
}


_QUERY_ALIASES = {
    "отель": ["hotel"],
    "отели": ["hotel"],
    "гостиница": ["hotel", "гостиница"],
    "гостиницы": ["hotel", "гостиница"],
    "бизнес центр": ["business center", "бизнес центр"],
    "бц": ["business center", "бизнес центр"],
    "торговый центр": ["shopping mall", "торговый центр"],
    "тц": ["shopping mall", "торговый центр"],
    "трц": ["shopping mall", "торговый центр"],
    "офисное здание": ["office building", "офисный центр"],
    "административное здание": ["office building", "административное здание"],
    "производственный комплекс": ["industrial building", "производственный комплекс"],
    "складской комплекс": ["warehouse", "складской комплекс"],
    "медицинский центр": ["medical center", "медицинский центр"],
    "автосалон": ["car dealership", "автосалон"],
    "ресторан отдельное здание": ["restaurant", "ресторан"],
    "банк отдельное здание": ["bank", "банк"],
}


def _queries(city: str, query: str) -> list[str]:
    raw = (query or "").strip()
    low = raw.lower().replace("ё", "е")
    slug = _CITY_SLUG.get((city or "").strip().lower().replace("ё", "е"), "")
    city_variants = [city.strip()]
    if slug:
        city_variants.append(slug)
    bases = _QUERY_ALIASES.get(low, [raw])
    out: list[str] = []
    for base in bases:
        for city_name in city_variants:
            q = f"{base} {city_name}".strip()
            if q and q not in out:
                out.append(q)
    return out


class TwoGisObjectProvider:
    URL = "https://catalog.api.2gis.com/3.0/items"

    async def search(self, city: str, query: str, count: int) -> list[ObjectCandidate]:
        if not settings.twogis_api_key:
            return []
        slug = _CITY_SLUG.get((city or "").strip().lower().replace("ё", "е"), "")
        out: list[ObjectCandidate] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=25) as client:
            for q in _queries(city, query):
                params = {
                    "q": q,
                    "key": settings.twogis_api_key,
                    "page_size": min(max(count, 5), 10),
                    "fields": "items.point,items.address_name,items.full_name,items.building_name,items.rubrics,items.type,items.subtype,items.purpose_name",
                }
                response = await client.get(self.URL, params=params)
                response.raise_for_status()
                rows = ((response.json().get("result") or {}).get("items") or [])
                for row in rows:
                    point = row.get("point") or {}
                    rid = str(row.get("id") or "")
                    if rid in seen:
                        continue
                    seen.add(rid)
                    rubrics = ", ".join(
                        str((x or {}).get("name") or "")
                        for x in (row.get("rubrics") or [])
                        if (x or {}).get("name")
                    )
                    if slug and rid:
                        source_url = f"https://2gis.ru/{slug}/firm/{rid}"
                    elif rid:
                        source_url = f"https://2gis.ru/search/{rid}"
                    else:
                        source_url = f"https://2gis.ru/search/{q}"
                    out.append(
                        ObjectCandidate(
                            external_id=f"2gis-{rid or len(out)}",
                            name=(
                                row.get("building_name")
                                or row.get("name")
                                or row.get("full_name")
                                or "Коммерческое здание"
                            ),
                            address=row.get("address_name") or row.get("full_name") or city,
                            lat=point.get("lat"),
                            lon=point.get("lon"),
                            category=rubrics or row.get("purpose_name") or ((row.get("type") or "") + " " + (row.get("subtype") or "")).strip(),
                            source_url=source_url,
                            source_provider="2gis-api",
                        )
                    )
                    if len(out) >= count:
                        return out
        return out
