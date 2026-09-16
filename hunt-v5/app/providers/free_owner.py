"""Free building → legal entity resolver (DaData + List-Org + open web). Not cadastral proof."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.providers.free_web import HEADERS, web_links
from app.providers.known_public_sources import known_public_owner

log = logging.getLogger(__name__)
_INN_RE = re.compile(r"(?<!\d)(\d{10}|\d{12})(?!\d)")
_BAD_ORG = re.compile(
    r"профсоюз|ппоо|первичн|филиал|дочерн|представительств",
    re.I,
)


@dataclass
class OwnerHit:
    inn: str
    source: str
    query: str = ""
    confidence: int = 50


def core_title(title: str) -> str:
    """Yandex titles are 'Name, category, City, street…' — keep the place name."""
    raw = (title or "").strip()
    if not raw:
        return ""
    first = raw.split(",")[0].strip()
    first = re.sub(r"\s+", " ", first)
    return first[:120]


def _uniq_inns(values: list[str], limit: int = 10) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
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


def _name_overlap(query: str, company_name: str) -> int:
    qt = {
        t
        for t in re.findall(r"[a-zа-яё0-9]{4,}", (query or "").lower().replace("ё", "е"))
        if t not in {"завод", "общество", "акционерное", "оборудование", "компания", "город"}
    }
    if not qt:
        return 0
    blob = (company_name or "").lower().replace("ё", "е")
    return int(100 * sum(1 for t in qt if t in blob) / max(len(qt), 1))


class FreeOwnerProvider:
    async def resolve(
        self, *, title: str, address: str, city: str, cadastral_number: str = ""
    ) -> OwnerHit | None:
        name = core_title(title) or title
        known = known_public_owner(name, address, city)
        if known:
            return OwnerHit(
                inn=known["inn"],
                source="known-public-source",
                query=known["source"],
                confidence=int(known.get("confidence") or 70),
            )
        hits: list[OwnerHit] = []
        async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            # For buildings, address/cadastre evidence is stronger than POI-name
            # matching. Name-only company suggestions often point to a tenant.
            hits.extend(await self._web(client, name, address, city, cadastral_number))
            hits.extend(await self._list_org(client, name, city, cadastral_number))
            hits.extend(await self._dadata_suggest(client, name, address, city))
        if not hits:
            return None
        rank = {"dadata": 3, "list-org": 2, "web": 1}
        hits.sort(
            key=lambda h: (
                h.confidence,
                _name_overlap(name, h.query),
                rank.get(h.source, 0),
            ),
            reverse=True,
        )
        return hits[0]

    async def _list_org(
        self, client: httpx.AsyncClient, title: str, city: str, cadastral_number: str = ""
    ) -> list[OwnerHit]:
        out: list[OwnerHit] = []
        queries = [f"{title} {city}".strip(), title]
        if cadastral_number:
            queries.insert(0, cadastral_number)
        for query in queries:
            try:
                resp = await client.get(
                    "https://www.list-org.com/search",
                    params={"type": "all", "val": query},
                    timeout=12.0,
                )
            except Exception:
                continue
            if resp.status_code >= 400 or not resp.text:
                continue
            for inn in _uniq_inns(_INN_RE.findall(resp.text[:220_000]), 6):
                out.append(OwnerHit(inn=inn, source="list-org", query=query, confidence=55))
            if out:
                break
        return out

    async def _web(
        self, client: httpx.AsyncClient, title: str, address: str, city: str, cadastral_number: str = ""
    ) -> list[OwnerHit]:
        queries = [
            f'"{cadastral_number}" собственник ИНН' if cadastral_number else "",
            f'"{cadastral_number}" правообладатель ИНН' if cadastral_number else "",
            f'"{cadastral_number}" владелец здания ИНН' if cadastral_number else "",
            f'"{address}" собственник ИНН' if address else "",
            f'"{address}" правообладатель ИНН' if address else "",
            f'"{address}" владелец здания ИНН' if address else "",
            f'"{address}" управляющая компания ИНН' if address else "",
            f'"{title}" {city} ИНН',
            f'"{title}" "{address}" ИНН' if address else "",
            f'"{title}" {city} АО ИНН',
            f'"{title}" {city} владелец здания',
        ]
        inns: list[str] = []
        for q in [x for x in queries if x][:5]:
            links = await web_links(client, q, limit=8)
            for url in links:
                host = url.lower()
                if not any(x in host for x in ("list-org.", "rusprofile.", "checko.", "sbis.")):
                    continue
                try:
                    resp = await client.get(url, timeout=10.0)
                    inns.extend(_INN_RE.findall(resp.text[:180_000] if resp.text else ""))
                except Exception:
                    continue
        return [OwnerHit(inn=i, source="web", query=title, confidence=45) for i in _uniq_inns(inns, 6)]

    async def _dadata_suggest(
        self, client: httpx.AsyncClient, title: str, address: str, city: str
    ) -> list[OwnerHit]:
        if not settings.dadata_api_key:
            return []
        headers = {
            "Authorization": f"Token {settings.dadata_api_key}",
            "Content-Type": "application/json",
        }
        out: list[OwnerHit] = []
        seen: set[str] = set()
        for query in (title, f"{title} {city}".strip()):
            if not (query or "").strip() or len(query) > 100:
                continue
            try:
                r = await client.post(
                    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party",
                    headers=headers,
                    json={"query": query, "count": 8},
                    timeout=15.0,
                )
                r.raise_for_status()
                for item in (r.json() or {}).get("suggestions") or []:
                    data = item.get("data") or {}
                    inn = str(data.get("inn") or "")
                    if not inn or inn in seen:
                        continue
                    cname = (
                        ((data.get("name") or {}).get("short_with_opf") or "")
                        or ((data.get("name") or {}).get("full_with_opf") or "")
                        or item.get("value")
                        or ""
                    )
                    if _BAD_ORG.search(cname):
                        continue
                    if str(data.get("branch_type") or "").upper() == "BRANCH":
                        continue
                    status = str((data.get("state") or {}).get("status") or "").upper()
                    if status and status not in ("ACTIVE", "REORGANIZING"):
                        continue
                    overlap = _name_overlap(title, cname)
                    if overlap < 50:
                        continue
                    conf = 45 + min(overlap, 20)
                    if str(data.get("branch_type") or "").upper() == "MAIN":
                        conf += 10
                    if re.search(r'^(АО|ПАО|ООО)\b', cname, re.I):
                        conf += 5
                    seen.add(inn)
                    out.append(OwnerHit(inn=inn, source="dadata-name-match", query=cname, confidence=min(conf, 72)))
            except Exception as exc:
                log.info("dadata suggest failed: %s", exc)
        out.sort(key=lambda h: h.confidence, reverse=True)
        return out
