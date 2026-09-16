"""Visual evidence: free Yandex org photos + image search. No Maps API key required."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, quote_plus

import httpx

from app.config import settings
from app.providers.free_web import HEADERS

log = logging.getLogger(__name__)
BAD_IMAGE_URL_RE = re.compile(
    r"logo|icon|sprite|avatar|placeholder|blank|1x1|interior|inside|menu|food|dish|banner",
    re.I,
)


@dataclass
class VisualEvidence:
    photo_url: str = ""
    photo_source_url: str = ""
    photo_source_type: str = ""
    panorama_available: bool = False
    panorama_lat: float | None = None
    panorama_lon: float | None = None
    map_url: str = ""
    confidence: int = 0


class VisualEvidenceProvider:
    NOMINATIM = "https://nominatim.openstreetmap.org/search"

    async def enrich(
        self,
        *,
        name: str,
        address: str,
        lat: float | None,
        lon: float | None,
        existing_photo_url: str = "",
        existing_source_url: str = "",
    ) -> VisualEvidence:
        existing_ok = bool(existing_photo_url and not BAD_IMAGE_URL_RE.search(existing_photo_url))
        out = VisualEvidence(
            photo_url=existing_photo_url if existing_ok else "",
            photo_source_url=existing_source_url if existing_ok else "",
            photo_source_type="source_object_photo" if existing_ok else "",
            panorama_lat=lat,
            panorama_lon=lon,
            confidence=80 if existing_photo_url else 0,
        )

        async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            if (out.panorama_lat is None or out.panorama_lon is None) and address:
                try:
                    r = await client.get(
                        self.NOMINATIM,
                        params={
                            "q": address,
                            "format": "jsonv2",
                            "limit": 1,
                            "countrycodes": "ru",
                        },
                        headers={"User-Agent": settings.user_agent},
                    )
                    r.raise_for_status()
                    rows = r.json()
                    if rows:
                        out.panorama_lat = float(rows[0]["lat"])
                        out.panorama_lon = float(rows[0]["lon"])
                except Exception:
                    pass

            if not out.photo_url and existing_source_url and "yandex." in existing_source_url and "/maps/org" in existing_source_url:
                try:
                    r = await client.get(existing_source_url, timeout=14.0)
                    photo = self._altay(r.text or "")
                    if photo:
                        out.photo_url = photo
                        out.photo_source_url = existing_source_url
                        out.photo_source_type = "yandex-maps-org"
                        out.confidence = max(out.confidence, 75)
                except Exception as exc:
                    log.info("yandex org photo failed: %s", exc)

            if not out.photo_url:
                photo = await self._yandex_images(client, name, address)
                if photo:
                    out.photo_url = photo
                    out.photo_source_url = (
                        f"https://yandex.ru/images/search?text={quote_plus(f'{name} {address} фасад')}"
                    )
                    out.photo_source_type = "yandex-images-free"
                    out.confidence = max(out.confidence, 55)

            if not out.photo_url and settings.public_image_search_api_url:
                try:
                    headers = {}
                    if settings.public_image_search_api_key:
                        headers["Authorization"] = f"Bearer {settings.public_image_search_api_key}"
                    r = await client.get(
                        settings.public_image_search_api_url,
                        params={"q": f'"{name}" "{address}" фасад здание'},
                        headers=headers,
                    )
                    r.raise_for_status()
                    images = (r.json() or {}).get("images") or []
                    if images:
                        first = images[0]
                        out.photo_url = first.get("url", "")
                        out.photo_source_url = first.get("source_url", "")
                        out.photo_source_type = "public_image_search"
                        out.confidence = max(out.confidence, 60)
                except Exception:
                    pass

        if out.panorama_lat is not None and out.panorama_lon is not None:
            out.map_url = (
                "https://yandex.ru/maps/?ll="
                f"{out.panorama_lon:.6f}%2C{out.panorama_lat:.6f}"
                "&z=17&l=map%2Cstv"
            )
            # Public map/panorama link works in browser without API key.
            out.panorama_available = True
            out.confidence = max(out.confidence, 70)
        elif address or name:
            out.map_url = f"https://yandex.ru/maps/?text={quote(f'{name} {address}'.strip())}"

        return out

    @staticmethod
    def _altay(html: str) -> str:
        for m in re.finditer(
            r"https://avatars\.mds\.yandex\.net/get-altay/(\d+)/([a-f0-9]+)",
            html or "",
            re.I,
        ):
            return f"https://avatars.mds.yandex.net/get-altay/{m.group(1)}/{m.group(2)}/orig"
        return ""

    async def _yandex_images(self, client: httpx.AsyncClient, name: str, address: str) -> str:
        q = f"{name} {address} фасад здание снаружи вход улица панорама".strip()
        url = f"https://yandex.ru/images/search?text={quote_plus(q)}"
        try:
            resp = await client.get(url, timeout=18.0)
            html = resp.text or ""
        except Exception as exc:
            log.info("yandex images failed: %s", exc)
            return ""
        photo = self._altay(html)
        if photo:
            return photo
        for m in re.finditer(
            r'(//avatars\.mds\.yandex\.net/i\?id=[^\"\'&\s]+)',
            html,
        ):
            return "https:" + m.group(1).split("&")[0]
        for m in re.finditer(r'"(https://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', html, re.I):
            u = m.group(1)
            low = u.lower()
            if BAD_IMAGE_URL_RE.search(low):
                continue
            return u
        return ""
