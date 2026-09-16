"""Free object discovery: Yandex Maps /org + 2GIS HTML + Nominatim. No API keys required."""
from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from urllib.parse import quote_plus, unquote

import httpx

from app.config import settings
from app.providers.base import ObjectCandidate
from app.providers.free_web import HEADERS, web_links
from app.providers.known_public_sources import known_public_object_candidates
from app.providers.nominatim import NominatimObjectProvider
from app.providers.public_registry_objects import PublicRegistryObjectProvider
from app.providers.torgi_gov import TorgiGovProvider
from app.providers.twogis import TwoGisObjectProvider

log = logging.getLogger(__name__)

_CITY_SLUG = {
    "казань": "kazan",
    "москва": "moscow",
    "санкт-петербург": "spb",
    "спб": "spb",
    "екатеринбург": "ekaterinburg",
    "новосибирск": "novosibirsk",
}


def _clean_title(title: str) -> str:
    title = html_lib.unescape(title or "")
    title = re.split(r"\s[—\-·|]\s", title)[0].strip()
    return re.sub(r"\s+", " ", title)


def _looks_address(text: str) -> bool:
    low = (text or "").lower()
    if not low or len(low) < 8:
        return False
    if any(x in low for x in ("рейтинг", "отзыв", "⭐", "часы работы")):
        return False
    return any(
        x in low
        for x in ("ул.", "улиц", "просп", "пер.", "шоссе", "набер", "д.", "дом", "казань", "москва")
    )


def _extract_altay(html: str) -> str:
    for m in re.finditer(
        r"https://avatars\.mds\.yandex\.net/get-altay/(\d+)/([a-f0-9]+)",
        html or "",
        re.I,
    ):
        return f"https://avatars.mds.yandex.net/get-altay/{m.group(1)}/{m.group(2)}/orig"
    return ""


def _coords_from_html(html: str) -> tuple[float | None, float | None]:
    m = re.search(r'"coordinates"\s*:\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]', html or "")
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        # GeoJSON often [lon, lat]
        if 40 <= b <= 80 and 20 <= a <= 180:
            return b, a
        if 40 <= a <= 80 and 20 <= b <= 180:
            return a, b
    m = re.search(r'll=([-\d.]+)%2C([-\d.]+)', html or "", re.I)
    if m:
        return float(m.group(2)), float(m.group(1))
    return None, None


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-zа-яё0-9]{3,}", (text or "").lower().replace("ё", "е"))
        if t not in {"улица", "город", "завод", "компания", "организация", "проспект", "переулок"}
    }


def _name_score(query: str, name: str, address: str = "") -> int:
    qt = _tokens(query)
    if not qt:
        return 0
    blob = f"{name} {address}".lower().replace("ё", "е")
    hit = sum(1 for t in qt if t in blob)
    # Prefer exact-ish containment of the whole query core
    qn = re.sub(r"\s+", "", (query or "").lower().replace("ё", "е"))
    bn = re.sub(r"\s+", "", blob)
    bonus = 20 if qn and qn in bn else 0
    return int(100 * hit / max(len(qt), 1)) + bonus


def _generic_name_penalty(query: str, name: str) -> int:
    q = (query or "").lower().replace("ё", "е").strip()
    n = (name or "").lower().replace("ё", "е").strip()
    n = re.sub(r"[^a-zа-я0-9 ]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    generic = {
        "отель",
        "отели",
        "гостиница",
        "гостиницы",
        "бизнес центр",
        "торговый центр",
        "тц",
        "трц",
        "офисное здание",
        "административное здание",
        "производственный комплекс",
        "складской комплекс",
        "медицинский центр",
        "автосалон",
        "ресторан",
        "банк",
    }
    if n in generic or n == q:
        return -100
    if len(_tokens(n) - _tokens(q)) < 1:
        return -50
    return 0


def _provider_priority(provider: str) -> int:
    p = (provider or "").lower()
    if "known-public-source" in p:
        return 55
    if "torgi-gov" in p:
        return 52
    if "public-registry" in p:
        return 45
    if "2gis-api" in p:
        return 30
    if "yandex" in p:
        return 20
    if "2gis" in p:
        return 15
    if "nominatim" in p:
        return 5
    return 0


class FreeMapsObjectProvider:
    """Primary free path used by classic Niteos hunt (no Maps API keys)."""

    async def search(self, city: str, query: str, count: int) -> list[ObjectCandidate]:
        pool: list[ObjectCandidate] = []
        seen: set[str] = set()

        def add(items: list[ObjectCandidate]):
            for item in items:
                key = (item.source_url or f"{item.name}|{item.address}").lower()
                if key in seen:
                    continue
                seen.add(key)
                pool.append(item)

        add(known_public_object_candidates(city, query, max(count, 2)))
        async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
            try:
                add(
                    await asyncio.wait_for(
                        TorgiGovProvider().search(city, query, max(count, 2)),
                        timeout=14.0,
                    )
                )
            except Exception as exc:
                log.info("torgi.gov object search failed: %s", exc)
            try:
                add(
                    await asyncio.wait_for(
                        PublicRegistryObjectProvider().search(city, query, max(count, 2)),
                        timeout=12.0,
                    )
                )
            except Exception as exc:
                log.info("public registry object search failed: %s", exc)
            try:
                add(await TwoGisObjectProvider().search(city, query, max(count * 3, 6)))
            except Exception as exc:
                log.info("2gis api failed: %s", exc)
            add(await self._yandex_orgs(client, city, query, max(count * 3, 6)))
            add(await self._twogis_html(client, city, query, max(count * 3, 6)))
        try:
            add(await NominatimObjectProvider().search(city, query, max(count * 3, 6)))
        except Exception as exc:
            log.info("nominatim fallback failed: %s", exc)

        ranked = sorted(
            pool,
            key=lambda o: (
                _generic_name_penalty(query, o.name),
                _provider_priority(o.source_provider),
                _name_score(query, o.name, o.address),
                1 if o.photo_url else 0,
                1 if o.lat is not None else 0,
            ),
            reverse=True,
        )
        # Drop obvious mismatches when we have at least one decent hit
        good = [
            o
            for o in ranked
            if _name_score(query, o.name, o.address) >= 40
            or o.source_provider == "public-registry-free"
            or o.source_provider == "known-public-source"
            or o.source_provider == "torgi-gov-api"
        ]
        chosen = good if good else ranked
        return chosen[:count]

    async def _yandex_orgs(
        self, client: httpx.AsyncClient, city: str, query: str, limit: int
    ) -> list[ObjectCandidate]:
        q = f"{query} {city}".strip()
        searches = [
            f"{q} site:yandex.ru/maps/org",
            f'"{query}" {city} site:yandex.ru/maps/org',
            f"{q} яндекс карты организация",
        ]
        links: list[str] = []
        for s in searches:
            links.extend(await web_links(client, s, limit=12))
        out: list[ObjectCandidate] = []
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
            photo = ""
            lat = lon = None
            try:
                resp = await client.get(key, headers=HEADERS, timeout=14.0)
                html = resp.text or ""
            except Exception:
                html = ""
            if html:
                tm = re.search(
                    r'property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                    html,
                    re.I,
                ) or re.search(
                    r'content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
                    html,
                    re.I,
                ) or re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                if tm:
                    title = _clean_title(html_lib.unescape(tm.group(1)))
                am = re.search(
                    r'property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
                    html,
                    re.I,
                ) or re.search(
                    r'content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
                    html,
                    re.I,
                )
                if am:
                    cand = html_lib.unescape(am.group(1)).strip()
                    if _looks_address(cand):
                        address = cand
                photo = _extract_altay(html)
                lat, lon = _coords_from_html(html)
            if not title:
                m = re.search(r"/maps/org/([^/]+)/", key)
                if m:
                    title = _clean_title(unquote(m.group(1)).replace("_", " ").replace("-", " "))
            if not title or len(title) < 2:
                continue
            oid = re.search(r"/maps/org/[^/]+/(\d+)", key)
            out.append(
                ObjectCandidate(
                    external_id=f"yandex-{oid.group(1) if oid else len(out)}",
                    name=title,
                    address=address,
                    lat=lat,
                    lon=lon,
                    category="organization",
                    photo_url=photo,
                    source_url=key,
                    source_provider="yandex-maps-free",
                )
            )
            if len(out) >= limit:
                break
        return out

    async def _twogis_html(
        self, client: httpx.AsyncClient, city: str, query: str, limit: int
    ) -> list[ObjectCandidate]:
        slug = _CITY_SLUG.get((city or "").strip().lower().replace("ё", "е"), "")
        q = quote_plus(f"{query} {city}".strip())
        url = f"https://2gis.ru/{slug}/search/{q}" if slug else f"https://2gis.ru/search/{q}"
        try:
            resp = await client.get(url, headers=HEADERS, timeout=18.0)
            html = resp.text or ""
        except Exception as exc:
            log.info("2gis html failed: %s", exc)
            return []
        if len(html) < 800 or "captcha" in html.lower():
            return []
        out: list[ObjectCandidate] = []
        seen: set[str] = set()
        for m in re.finditer(
            r'href="(https://2gis\.ru/[^"]+/firm/[^"?#]+)"[^>]*>([^<]{2,120})<',
            html,
        ):
            firm_url, title = m.group(1).split("?")[0], html_lib.unescape(m.group(2)).strip()
            if firm_url in seen or len(title) < 2:
                continue
            seen.add(firm_url)
            out.append(
                ObjectCandidate(
                    external_id=f"2gis-html-{len(out)}",
                    name=title,
                    address=city,
                    source_url=firm_url,
                    source_provider="2gis-html-free",
                )
            )
            if len(out) >= limit:
                break
        if out:
            return out
        # JSON blobs sometimes embed firm names
        for m in re.finditer(r'"name"\s*:\s*"([^"]{2,80})".{0,200}?"address_name"\s*:\s*"([^"]{0,120})"', html):
            title, addr = html_lib.unescape(m.group(1)), html_lib.unescape(m.group(2) or city)
            key = f"{title}|{addr}"
            if key in seen:
                continue
            seen.add(key)
            out.append(
                ObjectCandidate(
                    external_id=f"2gis-html-{len(out)}",
                    name=title,
                    address=addr or city,
                    source_url=url,
                    source_provider="2gis-html-free",
                )
            )
            if len(out) >= limit:
                break
        return out
