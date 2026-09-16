from __future__ import annotations

import hashlib
import html as html_lib
import re

import httpx

from app.providers.base import ObjectCandidate
from app.providers.free_cadastre_web import CAD_RE
from app.providers.free_web import HEADERS, web_links
from app.providers.known_public_sources import known_public_object_candidates


_BAD_URL_PARTS = ("yandex.ru/maps", "2gis.ru", "google.", "youtube.", "avito.ru")
_TRUSTED_URL_PARTS = (
    "torgi.gov.ru",
    "new.etpgpb.ru",
    "fedresurs.ru",
    "rosim.gov.ru",
    "rts-tender.ru",
    "sberbank-ast.ru",
)
_ADDRESS_RE = re.compile(
    r"(?:адрес|местоположение|расположен[оа] по адресу)[^\n.;:]{0,80}"
    r"((?:республика\s+татарстан,\s*)?(?:г\.?\s*)?[А-ЯЁA-Z][^.;\n]{8,180})",
    re.I,
)


def _text(html: str) -> str:
    raw = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html_lib.unescape(raw)).strip()


def _title(html: str, url: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    if not m:
        return url
    title = re.sub(r"\s+", " ", html_lib.unescape(m.group(1))).strip()
    title = re.sub(r"\s[|—-]\s.*$", "", title).strip()
    return title[:140] or url


def _city_seen(city: str, text: str) -> bool:
    city_core = (city or "").lower().replace("ё", "е").strip()
    blob = (text or "").lower().replace("ё", "е")
    return bool(city_core and city_core in blob)


def _query_seen(query: str, text: str) -> bool:
    tokens = {
        t
        for t in re.findall(r"[a-zа-яё0-9]{4,}", (query or "").lower().replace("ё", "е"))
        if t not in {"здание", "коммерческое", "центр"}
    }
    if not tokens:
        return True
    blob = (text or "").lower().replace("ё", "е")
    return any(t in blob or t[:5] in blob for t in tokens)


def _query_terms(query: str) -> list[str]:
    low = (query or "").lower().replace("ё", "е")
    terms = [query.strip()] if query.strip() else []
    aliases = []
    if "отел" in low or "гостиниц" in low:
        aliases = ["отель", "гостиница"]
    elif "склад" in low:
        aliases = ["склад", "здание склада"]
    elif "производ" in low or "пром" in low:
        aliases = ["производственная база", "производственное здание"]
    elif "бизнес" in low or "офис" in low:
        aliases = ["офисное здание", "административное здание"]
    elif "торгов" in low or "тц" in low or "трц" in low:
        aliases = ["торговое здание", "торговый центр"]
    for alias in aliases:
        if alias and alias not in terms:
            terms.append(alias)
    return terms[:2] or [query]


def _address(city: str, text: str) -> str:
    m = _ADDRESS_RE.search(text or "")
    if not m:
        return city
    value = re.sub(r"\s+", " ", m.group(1)).strip(" .,:;")
    return value[:220] or city


class PublicRegistryObjectProvider:
    """Find building candidates on public pages that often include cadastre/owner data."""

    async def search(self, city: str, query: str, count: int) -> list[ObjectCandidate]:
        seeded = known_public_object_candidates(city, query, count)
        if seeded:
            return seeded
        searches = []
        for term in _query_terms(query):
            searches.extend(
                [
                    f'{city} {term} кадастровый номер site:torgi.gov.ru',
                    f'{city} {term} кадастровый номер site:new.etpgpb.ru',
                    f'"{city}" "{term}" "кадастровый номер" собственник',
                ]
            )
        out: list[ObjectCandidate] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=12, headers=HEADERS, follow_redirects=True) as client:
            for search in searches[:4]:
                for url in await web_links(client, search, limit=3):
                    key = url.split("#")[0]
                    low = key.lower()
                    if key in seen or any(part in low for part in _BAD_URL_PARTS):
                        continue
                    if not any(part in low for part in _TRUSTED_URL_PARTS):
                        continue
                    seen.add(key)
                    candidate = await self._candidate_from_url(client, city, query, key)
                    if candidate:
                        out.append(candidate)
                        if len(out) >= count:
                            return out
        return out

    async def _candidate_from_url(
        self, client: httpx.AsyncClient, city: str, query: str, url: str
    ) -> ObjectCandidate | None:
        try:
            response = await client.get(url, timeout=8.0)
        except Exception:
            return None
        if response.status_code >= 400 or not response.text:
            return None
        html = response.text[:350_000]
        text = _text(html)
        if not CAD_RE.search(text) or not _city_seen(city, text) or not _query_seen(query, text):
            return None
        title = _title(html, url)
        address = _address(city, text)
        external_id = hashlib.sha1(url.encode("utf-8")).hexdigest()[:18]
        return ObjectCandidate(
            external_id=f"public-registry-{external_id}",
            name=title,
            address=address,
            category=query,
            source_url=url,
            source_provider="public-registry-free",
        )
