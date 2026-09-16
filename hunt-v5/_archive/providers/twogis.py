from __future__ import annotations

import httpx

from app.config import settings
from app.providers.base import ObjectCandidate


class TwoGisObjectProvider:
    """2GIS Places API object/organization discovery.

    Requires `TWOGIS_API_KEY`. It returns operating organizations/buildings and their
    coordinates/addresses. Photos are intentionally handled elsewhere because 2GIS Places
    can filter by photo availability but does not expose photo files through this API.
    """

    URL = "https://catalog.api.2gis.com/3.0/items"

    async def search(self, city: str, query: str, count: int):
        if not settings.twogis_api_key:
            return []
        params = {
            "q": f"{query} {city}",
            "key": settings.twogis_api_key,
            "page_size": min(max(count, 1), 50),
            "fields": "items.point,items.address_name,items.full_name,items.contact_groups,items.org,items.rubrics",
        }
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(self.URL, params=params)
            r.raise_for_status()
            data = r.json()
        rows = ((data.get("result") or {}).get("items") or [])
        out = []
        for row in rows[:count]:
            point = row.get("point") or {}
            out.append(ObjectCandidate(
                external_id=f"2gis-{row.get('id','')}",
                name=row.get("name") or row.get("full_name") or "Объект",
                address=row.get("address_name") or row.get("full_name") or "",
                lat=point.get("lat"), lon=point.get("lon"),
                category=((row.get("type") or "") + " " + (row.get("subtype") or "")).strip(),
                source_url=f"https://2gis.ru/search/{row.get('id','')}",
                source_provider="2GIS Places API",
            ))
        return out
