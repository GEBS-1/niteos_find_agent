from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Any

import httpx

from app.providers.base import CadastreRecord, ObjectCandidate
from app.providers.free_cadastre_web import CAD_RE, INN_RE
from app.providers.free_web import HEADERS

log = logging.getLogger(__name__)

BASE = "https://torgi.gov.ru"
REAL_ESTATE_CAT = "7"
REGION_CODES = {
    "казань": "16",
    "татарстан": "16",
    "москва": "77",
    "санкт-петербург": "78",
    "спб": "78",
    "екатеринбург": "66",
    "новосибирск": "54",
}
OWNER_RE = re.compile(
    r"(?:собственник|продавец|правообладател[ья]|балансодержател|организатор)[^\n;:]{0,120}"
    r"((?:ООО|АО|ПАО|ЗАО|ОАО|ФГУП|МУП|ГБУ|ГАУ|МКУ)\s+[\"«]?[A-ZА-ЯЁ0-9][^.;,\n]{3,180})",
    re.I,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е")).strip()


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(html_lib.unescape(value))
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(_strings(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_strings(item))
    return out


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", " ".join(_strings(value))).strip()


def _pick(obj: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return str(obj[key])
    low = {str(k).lower(): v for k, v in obj.items()}
    for key in keys:
        v = low.get(key.lower())
        if v not in (None, ""):
            return str(v)
    return ""


def _first_item(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "items", "data", "result", "results", "lotCards"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _first_item(value)
            if nested:
                return nested
    return []


def _lot_id(item: dict[str, Any]) -> str:
    direct = _pick(item, "id", "lotId", "lotCardId", "lotNumber", "lotNumberFull")
    if direct:
        return direct
    blob = _text(item)
    m = re.search(r"\b\d{14,24}_\d+\b", blob)
    return m.group(0) if m else ""


def _source_url(lot_id: str) -> str:
    return f"{BASE}/new/public/lots/lot/{lot_id}/(lotInfo:info)" if lot_id else BASE


def _name(item: dict[str, Any], fallback: str = "") -> str:
    for obj in _walk(item):
        value = _pick(
            obj,
            "lotName",
            "name",
            "title",
            "subject",
            "lotDescription",
            "description",
            "propertyName",
        )
        if value and len(value) > 4:
            return re.sub(r"\s+", " ", value).strip()[:240]
    return fallback or "Лот недвижимости ГИС Торги"


def _address(item: dict[str, Any], fallback: str = "") -> str:
    for obj in _walk(item):
        value = _pick(
            obj,
            "estateAddress",
            "address",
            "location",
            "propertyLocation",
            "lotLocation",
            "objectAddress",
        )
        if value and len(value) > 5:
            return re.sub(r"\s+", " ", value).strip()[:260]
    text = _text(item)
    m = re.search(r"(?:адрес|местонахождение)[^\n;:]{0,80}([А-ЯЁA-Z][^;\n]{8,180})", text, re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:260] if m else fallback


def _owner_name(text: str) -> str:
    m = OWNER_RE.search(text or "")
    return re.sub(r"\s+", " ", m.group(1)).strip(" .,:;") if m else ""


def _owner_inn(text: str) -> str:
    for owner_word in re.finditer(r"собственник|продавец|правообладател|балансодержател", text or "", re.I):
        window = text[max(owner_word.start() - 400, 0): owner_word.end() + 1000]
        m = INN_RE.search(window)
        if m and len(m.group(1)) == 10:
            return m.group(1)
    for inn in INN_RE.findall(text or ""):
        if len(inn) == 10:
            return inn
    return ""


def _region_code(city: str) -> str:
    low = _norm(city)
    for key, code in REGION_CODES.items():
        if key in low:
            return code
    return ""


class TorgiGovProvider:
    """Official public GIS Torgi estate provider.

    The API is useful but unstable/rate-limited, so this provider must soft-fail.
    """

    async def search(self, city: str, query: str, count: int) -> list[ObjectCandidate]:
        region = _region_code(city)
        if not region:
            return []
        params = {
            "lotStatus": ["PUBLISHED", "APPLICATIONS_SUBMISSION"],
            "dynSubjRF": region,
            "catCode": REAL_ESTATE_CAT,
            "size": min(max(count * 4, 4), 20),
            "page": 0,
            "sort": "firstVersionPublicationDate,desc",
        }
        out: list[ObjectCandidate] = []
        try:
            async with httpx.AsyncClient(timeout=14, headers=HEADERS, verify=False) as client:
                response = await client.get(f"{BASE}/new/api/public/lotcards/search", params=params)
                response.raise_for_status()
                data = response.json()
                for item in _first_item(data):
                    cand = self._candidate_from_item(city, query, item)
                    if cand:
                        out.append(cand)
                    if len(out) >= count:
                        break
        except Exception as exc:
            log.info("torgi.gov search failed: %s", exc)
        return out

    def _candidate_from_item(
        self, city: str, query: str, item: dict[str, Any]
    ) -> ObjectCandidate | None:
        blob = _norm(_text(item))
        if query and not any(token in blob for token in _query_tokens(query)):
            return None
        lot_id = _lot_id(item)
        name = _name(item)
        address = _address(item, city)
        if not lot_id and not CAD_RE.search(blob):
            return None
        return ObjectCandidate(
            external_id=f"torgi-gov-{lot_id or abs(hash(blob))}",
            name=name,
            address=address,
            category="estate_auction",
            source_url=_source_url(lot_id),
            source_provider="torgi-gov-api",
        )


def _query_tokens(query: str) -> list[str]:
    low = _norm(query)
    aliases = []
    if "склад" in low:
        aliases = ["склад", "производ", "база"]
    elif "отел" in low or "гостиниц" in low:
        aliases = ["отел", "гостиниц"]
    elif "бизнес" in low or "офис" in low:
        aliases = ["офис", "административ", "делов"]
    elif "торгов" in low or "тц" in low:
        aliases = ["торгов", "магазин"]
    return aliases or [t[:6] for t in re.findall(r"[a-zа-яё0-9]{4,}", low)]


class TorgiGovCadastreProvider:
    async def resolve(self, obj: ObjectCandidate) -> CadastreRecord | None:
        lot_id = ""
        m = re.search(r"/lot/([^/?#(]+)", obj.source_url or "")
        if m:
            lot_id = m.group(1)
        if not lot_id and obj.external_id.startswith("torgi-gov-"):
            lot_id = obj.external_id.removeprefix("torgi-gov-")
        if not lot_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=14, headers=HEADERS, verify=False) as client:
                response = await client.get(f"{BASE}/new/api/public/lotcards/{lot_id}")
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            log.info("torgi.gov detail failed %s: %s", lot_id, exc)
            return None
        return self._cadastre_from_detail(obj, lot_id, data)

    def _cadastre_from_detail(
        self, obj: ObjectCandidate, lot_id: str, data: Any
    ) -> CadastreRecord | None:
        text = _text(data)
        cad = CAD_RE.search(text)
        if not cad:
            return None
        owner_inn = _owner_inn(text)
        owner_name = _owner_name(text)
        return CadastreRecord(
            cadastral_number=cad.group(0),
            address=_address(data if isinstance(data, dict) else {}, obj.address),
            area=None,
            cadastral_value=None,
            owner_type="legal_entity" if owner_inn else "",
            owner_name=owner_name,
            owner_inn=owner_inn,
            owner_ogrn="",
            source="torgi-gov-api",
            source_url=_source_url(lot_id),
            match_confidence=92 if owner_inn else 82,
        )
