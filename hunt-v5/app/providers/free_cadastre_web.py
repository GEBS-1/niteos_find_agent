from __future__ import annotations

import html as html_lib
import logging
import re

import httpx

from app.providers.base import CadastreRecord, ObjectCandidate
from app.providers.free_web import HEADERS, web_links

log = logging.getLogger(__name__)

CAD_RE = re.compile(r"\b\d{2}:\d{2}:\d{6,10}:\d{1,8}\b")
INN_RE = re.compile(r"(?<!\d)(\d{10}|\d{12})(?!\d)")
AREA_RE = re.compile(
    r"(?:площад[ьиь]|общая площадь|area)[^\d]{0,40}([\d\s.,]{2,14})\s*(?:кв\.?\s*м|м2|м²)",
    re.I,
)
OWNER_WORDS = re.compile(r"собственник|правообладател|продавец|владелец|балансодержател", re.I)
TRUSTED_HOSTS = (
    "torgi.gov.ru",
    "new.etpgpb.ru",
    "fedresurs.ru",
    "rosim.gov.ru",
    "rts-tender.ru",
    "sberbank-ast.ru",
)
SKIP_SOURCE_HOSTS = (
    "yandex.ru/maps",
    "2gis.ru",
    "google.",
    "youtube.",
)


def _text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html_lib.unescape(html)).strip()


def _float(raw: str):
    try:
        return float((raw or "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _owner_inn_near(text: str) -> str:
    matches = list(INN_RE.finditer(text or ""))
    if not matches:
        return ""
    for marker in OWNER_WORDS.finditer(text or ""):
        start = max(marker.start() - 500, 0)
        end = marker.end() + 900
        window = text[start:end]
        m = INN_RE.search(window)
        if m:
            return m.group(1)
    return matches[0].group(1)


def _owner_name_near(text: str) -> str:
    m = re.search(
        r"(?:собственник|правообладател[ья]|продавец|владелец)[^\n.;:]{0,80}"
        r"((?:ООО|АО|ПАО|ЗАО|ОАО)\s+[\"«][^\"»]{3,160}[\"»]|"
        r"(?:ООО|АО|ПАО|ЗАО|ОАО)\s+[A-ZА-ЯЁ0-9][^.;,\n]{3,160})",
        text or "",
        re.I,
    )
    return re.sub(r"\s+", " ", m.group(1)).strip(" .,:;") if m else ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е")).strip()


def _street_hint(address: str) -> str:
    m = re.search(
        r"(?:ул\.?|улица|пр\.?|проспект|пер\.?|переулок|шоссе|наб\.?|набережная)"
        r"\s*[A-Za-zА-Яа-яЁё0-9\-\s]{3,60}",
        address or "",
        re.I,
    )
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


def _house_hint(address: str) -> str:
    m = re.search(r"(?:^|[, ])(?:д\.?|дом)?\s*(\d+[а-яa-z]?(?:/\d+)?)\b", _norm(address), re.I)
    return (m.group(1) if m else "").strip()


def _name_core(name: str) -> str:
    return re.split(r"[,—|]", name or "")[0].strip()


def _evidence_score(obj: ObjectCandidate, snippet: str, full_text: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    blob = _norm(snippet)
    page = _norm(full_text)
    street = _street_hint(obj.address)
    house = _house_hint(obj.address)
    if street and _norm(street) in blob:
        score += 3
        reasons.append("street_near_cadastre")
    elif street and _norm(street) in page:
        score += 1
        reasons.append("street_on_page")
    if house and re.search(rf"\b{re.escape(house)}\b", blob):
        score += 1
        reasons.append("house_near_cadastre")
    name = _name_core(obj.name)
    if name and len(name) >= 4 and _norm(name) in blob:
        score += 2
        reasons.append("name_near_cadastre")
    elif name and len(name) >= 4 and _norm(name) in page:
        score += 1
        reasons.append("name_on_page")
    if OWNER_WORDS.search(snippet):
        score += 1
        reasons.append("owner_words_near")
    return score, reasons


class FreeCadastreWebProvider:
    """Open-web cadastre fallback.

    This is not an EGRN substitute. It extracts cadastral numbers and publicly
    published owner/operator traces from pages such as auctions, government
    procurement, registry cards, PDF snippets and real-estate listings.
    """

    async def resolve(self, obj: ObjectCandidate) -> CadastreRecord | None:
        if not (obj.address or obj.name):
            return None
        queries = self._queries(obj)
        async with httpx.AsyncClient(timeout=18, headers=HEADERS, follow_redirects=True) as client:
            if obj.source_url and not any(x in obj.source_url.lower() for x in SKIP_SOURCE_HOSTS):
                cad = await self._from_url(client, obj, obj.source_url)
                if cad:
                    return cad
            for query in queries:
                links = await web_links(client, query, limit=5)
                for url in links[:5]:
                    cad = await self._from_url(client, obj, url)
                    if cad:
                        return cad
        return None

    def _queries(self, obj: ObjectCandidate) -> list[str]:
        address = " ".join(x.strip() for x in (obj.address or "").split(",")[:4] if x.strip())
        name = (obj.name or "").strip()
        values = [
            f'"{address}" "кадастровый номер"',
            f'"{name}" "{address}" кадастровый номер',
            f'"{address}" собственник ИНН',
            f'"{name}" "{address}" собственник ИНН',
            f'"{address}" site:torgi.gov.ru кадастровый',
            f'"{address}" site:new.etpgpb.ru кадастровый',
            f'"{address}" site:fedresurs.ru кадастровый',
        ]
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            value = re.sub(r"\s+", " ", value).strip()
            key = value.lower().replace("ё", "е")
            if len(key) < 12 or key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out[:4]

    async def _from_url(
        self, client: httpx.AsyncClient, obj: ObjectCandidate, url: str
    ) -> CadastreRecord | None:
        low = (url or "").lower()
        if any(x in low for x in SKIP_SOURCE_HOSTS):
            return None
        try:
            response = await client.get(url, timeout=12.0)
        except Exception:
            return None
        if response.status_code >= 400 or not response.text:
            return None
        return self._record_from_text(obj, url, _text(response.text[:400_000]))

    def _record_from_text(self, obj: ObjectCandidate, url: str, text: str) -> CadastreRecord | None:
        cad_matches = list(CAD_RE.finditer(text or ""))
        if not cad_matches:
            return None
        trusted = any(host in (url or "").lower() for host in TRUSTED_HOSTS)
        selected = None
        selected_snippet = ""
        selected_score = -1
        selected_reasons: list[str] = []
        for cad_match in cad_matches[:8]:
            snippet = text[max(cad_match.start() - 1800, 0): cad_match.end() + 1800]
            score, reasons = _evidence_score(obj, snippet, text)
            if score > selected_score:
                selected = cad_match
                selected_snippet = snippet
                selected_score = score
                selected_reasons = reasons
        if not selected:
            return None
        # Reject generic pages with random cadastre numbers. Trusted auction/
        # registry sources may pass with slightly weaker text evidence, but not
        # with zero object evidence.
        if selected_score < (2 if trusted else 3):
            log.info(
                "free cadastre rejected low evidence url=%s score=%s reasons=%s",
                url,
                selected_score,
                selected_reasons,
            )
            return None
        area = None
        area_match = AREA_RE.search(selected_snippet) or AREA_RE.search(text)
        if area_match:
            area = _float(area_match.group(1))
        owner_inn = _owner_inn_near(selected_snippet)
        owner_name = _owner_name_near(selected_snippet)
        confidence = 50 + min(selected_score * 8, 28) + (12 if owner_inn else 0)
        return CadastreRecord(
            cadastral_number=selected.group(0),
            address=obj.address,
            area=area,
            cadastral_value=None,
            owner_type="legal_entity" if owner_inn and len(owner_inn) == 10 else "",
            owner_name=owner_name,
            owner_inn=owner_inn if len(owner_inn) == 10 else "",
            owner_ogrn="",
            source="free-web-cadastre",
            source_url=url,
            match_confidence=min(confidence, 90),
        )
