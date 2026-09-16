import hashlib
import re
import asyncio
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Hunt, ObjectEntity, Company, Person, Contact, HuntResult, OwnershipEdge
from app.providers.demo import (
    DemoObjectProvider,
    DemoCadastreProvider,
    DemoCompanyProvider,
    DemoContactProvider,
)
from app.providers.free_maps import FreeMapsObjectProvider
from app.providers.free_owner import FreeOwnerProvider, core_title
from app.providers.visual import VisualEvidenceProvider
from app.providers.cadastre_http import HttpCadastreProvider
from app.providers.nspd_cadastre import NspdCadastreProvider
from app.providers.free_cadastre_web import FreeCadastreWebProvider
from app.providers.dadata import DaDataCompanyProvider
from app.providers.base import ObjectCandidate
from app.providers.known_public_sources import known_public_cadastre
from app.providers.known_public_lpr import known_lpr_contacts, known_lpr_people
from app.providers.torgi_gov import TorgiGovCadastreProvider
from app.services.contact_enrichment import PublicPersonContactEnricher
from app.services.ownership import resolve_ultimate_owners
from app.services.scoring import score_contact

_ORG_MARKERS = re.compile(
    r"ооо|ао\b|пао|зао|общество|управляющ|акционерн|ответственност|\bук\b",
    re.I,
)


class FreeCadastreProvider:
    async def resolve(self, obj):
        cad = known_public_cadastre(obj)
        if cad:
            return cad
        if (obj.source_provider or "").startswith("torgi-gov"):
            cad = await TorgiGovCadastreProvider().resolve(obj)
            if cad:
                return cad
        nspd = NspdCadastreProvider()
        try:
            cad = await asyncio.wait_for(nspd.resolve(obj), timeout=8.0)
            if cad:
                return cad
        except Exception:
            pass
        try:
            return await asyncio.wait_for(FreeCadastreWebProvider().resolve(obj), timeout=8.0)
        except Exception:
            return None


def _person_fio(name: str) -> str:
    """Keep only human FIO; drop УК/ООО names from registries."""
    t = re.sub(r"\s+", " ", (name or "").strip())
    if len(t) < 5 or _ORG_MARKERS.search(t) or '"' in t or "«" in t:
        return ""
    parts = t.replace("-", " ").split()
    if len(parts) < 2 or len(parts) > 5:
        return ""
    if not all(re.match(r"^[А-ЯЁA-Z]", p) for p in parts):
        return ""
    return t


def _key(obj):
    raw = "|".join(
        [
            obj.external_id or "",
            (obj.address or "").lower(),
            str(round(obj.lat or 0, 5)),
            str(round(obj.lon or 0, 5)),
        ]
    )
    return hashlib.sha1(raw.encode()).hexdigest()


_BUILDING_FALLBACKS = [
    "бизнес центр",
    "торговый центр",
    "гостиница",
    "отель",
    "офисное здание",
    "административное здание",
    "производственный комплекс",
    "складской комплекс",
    "медицинский центр",
    "автосалон",
    "ресторан отдельное здание",
    "банк отдельное здание",
]

_REGION_CITIES = {
    "россия": ["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск"],
    "республика татарстан": ["Казань", "Набережные Челны", "Альметьевск"],
    "москва": ["Москва"],
    "московская область": ["Химки", "Красногорск", "Мытищи", "Одинцово"],
    "санкт-петербург": ["Санкт-Петербург"],
    "свердловская область": ["Екатеринбург", "Нижний Тагил"],
    "новосибирская область": ["Новосибирск"],
    "краснодарский край": ["Краснодар", "Сочи"],
    "нижегородская область": ["Нижний Новгород"],
    "самарская область": ["Самара", "Тольятти"],
}


def _map_search_url(city: str, query: str) -> str:
    return f"https://yandex.ru/maps/?text={city.strip()}%20{query.strip()}"


def _scope_search_cities(city: str) -> list[str]:
    raw = (city or "").strip()
    if not raw:
        return [city]
    parts = [x.strip() for x in re.split(r"[,;]", raw) if x.strip()]
    if len(parts) > 1:
        out: list[str] = []
        seen: set[str] = set()
        for part in parts:
            for scope_city in _scope_search_cities(part):
                key = scope_city.lower().replace("ё", "е")
                if key in seen:
                    continue
                seen.add(key)
                out.append(scope_city)
        return out or [raw]
    scope_key = raw.lower().replace("ё", "е")
    return _REGION_CITIES.get(scope_key) or [raw]


def _append_unique_object(objects: list[ObjectCandidate], item: ObjectCandidate) -> bool:
    if item.external_id and any(o.external_id == item.external_id for o in objects):
        return False
    if item.address and any(o.address == item.address for o in objects):
        return False
    objects.append(item)
    return True


def _query_parts(query: str) -> list[str]:
    parts = [x.strip() for x in re.split(r"[,;]", query or "") if x.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for part in parts or [query]:
        key = part.lower().replace("ё", "е")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


async def _search_objects_for_query(
    object_provider,
    city: str,
    query: str,
    count: int,
    *,
    allow_placeholder: bool,
):
    search_cities = _scope_search_cities(city)
    objects: list[ObjectCandidate] = []
    per_city = max(1, (count + len(search_cities) - 1) // len(search_cities))
    for scope_city in search_cities:
        if len(objects) >= count:
            break
        try:
            found = await object_provider.search(scope_city, query, per_city)
        except Exception:
            found = []
        for item in found:
            _append_unique_object(objects, item)
            if len(objects) >= count:
                break
    if objects:
        return objects[:count]

    seen_queries = {query.strip().lower()}
    for alt in _BUILDING_FALLBACKS:
        if len(objects) >= count:
            break
        q = alt if alt.strip().lower() not in seen_queries else f"{alt} здание"
        seen_queries.add(q.strip().lower())
        for scope_city in search_cities:
            if len(objects) >= count:
                break
            try:
                found = await object_provider.search(scope_city, q, max(1, count - len(objects)))
            except Exception:
                continue
            for item in found:
                _append_unique_object(objects, item)
                if len(objects) >= count:
                    break
    if objects:
        return objects[:count]

    if not allow_placeholder:
        return []

    return [
        ObjectCandidate(
            external_id=f"needs-review-{hashlib.sha1(f'{city}|{query}'.encode()).hexdigest()[:12]}",
            name=f"{query.strip()} — кандидат на ручную проверку",
            address=city.strip(),
            category="needs_review",
            source_url=_map_search_url(city, query),
            source_provider="needs-review",
        )
    ]


async def _search_objects_resilient(object_provider, city: str, query: str, count: int):
    queries = _query_parts(query)
    if len(queries) > 1:
        objects: list[ObjectCandidate] = []
        per_query = max(1, (count + len(queries) - 1) // len(queries))
        for part in queries:
            if len(objects) >= count:
                break
            found = await _search_objects_for_query(
                object_provider,
                city,
                part,
                max(per_query, count - len(objects)),
                allow_placeholder=False,
            )
            for item in found:
                _append_unique_object(objects, item)
                if len(objects) >= count:
                    break
        if objects:
            return objects[:count]
    return await _search_objects_for_query(
        object_provider,
        city,
        queries[0] if queries else query,
        count,
        allow_placeholder=True,
    )


def _upsert_object(db, obj):
    k = _key(obj)
    row = db.query(ObjectEntity).filter(ObjectEntity.external_id == k).first()
    if not row:
        row = ObjectEntity(
            external_id=k,
            name=obj.name,
            address=obj.address,
            lat=obj.lat,
            lon=obj.lon,
            category=obj.category,
            photo_url=obj.photo_url,
            source_url=obj.source_url,
            source_provider=obj.source_provider,
        )
        db.add(row)
    else:
        row.name = obj.name
        row.address = obj.address
        row.lat = obj.lat
        row.lon = obj.lon
        row.category = obj.category
        row.photo_url = obj.photo_url
        row.source_url = obj.source_url
        row.source_provider = obj.source_provider
    db.flush()
    return row


def _upsert_company(db, r):
    row = db.query(Company).filter(Company.inn == r.inn).first()
    if not row:
        row = Company(inn=r.inn, name=r.name)
        db.add(row)
    row.name = r.name
    row.ogrn = r.ogrn
    row.legal_address = r.legal_address
    row.status = r.status
    row.revenue = r.revenue
    row.profit = r.profit
    row.employees = r.employees
    row.source = r.source_url or r.source
    db.flush()
    return row


def _add_contacts(db, person, owner_inn, candidates):
    for cc in candidates:
        score, status = score_contact(cc)
        exists = (
            db.query(Contact)
            .filter(
                Contact.person_id == person.id,
                Contact.contact_type == cc.contact_type,
                Contact.value == cc.value,
            )
            .first()
        )
        if not exists:
            db.add(
                Contact(
                    person_id=person.id,
                    company_inn=owner_inn,
                    contact_type=cc.contact_type,
                    value=cc.value,
                    source_url=cc.source_url,
                    source_type=cc.source_type,
                    is_direct_person_contact=cc.explicit_person_link,
                    name_match=cc.name_match,
                    company_match=cc.company_match,
                    role_match=cc.role_match,
                    city_match=cc.city_match,
                    explicit_person_link=cc.explicit_person_link,
                    confidence=score,
                    status=status,
                )
            )


async def _safe_person_contacts(contact_provider, person_name: str, company: str, city: str, role: str):
    if not contact_provider:
        return []
    try:
        return await asyncio.wait_for(
            contact_provider.search_person(person_name, company, city, role),
            timeout=12.0,
        )
    except Exception:
        return []


async def _attach_company_people(
    db,
    *,
    owner_inn: str,
    company_provider,
    contact_provider,
    company_fetcher,
    city: str,
):
    company_rec = await company_provider.by_inn(owner_inn)
    if not company_rec:
        return None
    _upsert_company(db, company_rec)
    db.query(OwnershipEdge).filter(OwnershipEdge.from_company_inn == owner_inn).delete()
    for f in company_rec.founders:
        db.add(
            OwnershipEdge(
                from_company_inn=owner_inn,
                to_kind=f.kind,
                to_name=f.name,
                to_company_inn=f.inn,
                share_percent=f.share_percent,
                source=f.source or company_rec.source,
            )
        )
    db.flush()
    ultimate = await resolve_ultimate_owners(owner_inn, company_fetcher)
    for u in ultimate:
        fio = _person_fio(u.full_name)
        if not fio:
            continue
        person = (
            db.query(Person)
            .filter(
                Person.full_name == fio,
                Person.company_inn == owner_inn,
                Person.role == "ultimate_identified_owner",
            )
            .first()
        )
        if not person:
            person = Person(
                full_name=fio,
                role="ultimate_identified_owner",
                company_inn=owner_inn,
            )
            db.add(person)
        person.effective_share = u.effective_share
        person.source = u.source
        db.flush()
        _add_contacts(
            db,
            person,
            owner_inn,
            await _safe_person_contacts(
                contact_provider, person.full_name, company_rec.name, city, person.role
            ),
        )
    director = _person_fio(company_rec.director_name or "")
    if director:
        drow = (
            db.query(Person)
            .filter(
                Person.full_name == director,
                Person.company_inn == owner_inn,
                Person.role == "general_director",
            )
            .first()
        )
        if not drow:
            drow = Person(
                full_name=director,
                role="general_director",
                company_inn=owner_inn,
                source=company_rec.source_url or company_rec.source,
            )
            db.add(drow)
            db.flush()
        _add_contacts(
            db,
            drow,
            owner_inn,
            await _safe_person_contacts(
                contact_provider, drow.full_name, company_rec.name, city, drow.role
            ),
        )
    for known in known_lpr_people(owner_inn):
        fio = _person_fio(known.get("full_name") or "")
        role = str(known.get("role") or "")
        if not fio or not role:
            continue
        krow = (
            db.query(Person)
            .filter(
                Person.full_name == fio,
                Person.company_inn == owner_inn,
                Person.role == role,
            )
            .first()
        )
        if not krow:
            krow = Person(
                full_name=fio,
                role=role,
                company_inn=owner_inn,
                source=str(known.get("source") or ""),
            )
            db.add(krow)
            db.flush()
        _add_contacts(db, krow, owner_inn, known_lpr_contacts(known))
    if contact_provider and hasattr(contact_provider, "search_role_people"):
        try:
            role_people = await asyncio.wait_for(
                contact_provider.search_role_people(company_rec.name, city, limit=4),
                timeout=14.0,
            )
        except Exception:
            role_people = []
        for found in role_people:
            fio = _person_fio(found.get("full_name") or "")
            role = str(found.get("role") or "")
            if not fio or not role:
                continue
            prow = (
                db.query(Person)
                .filter(
                    Person.full_name == fio,
                    Person.company_inn == owner_inn,
                    Person.role == role,
                )
                .first()
            )
            if not prow:
                prow = Person(
                    full_name=fio,
                    role=role,
                    company_inn=owner_inn,
                    source=str(found.get("source") or ""),
                )
                db.add(prow)
                db.flush()
            _add_contacts(
                db,
                prow,
                owner_inn,
                await _safe_person_contacts(
                    contact_provider, prow.full_name, company_rec.name, city, prow.role
                ),
            )
    return company_rec


async def run_hunt(db: Session, hunt: Hunt):
    hunt.status = "running"
    hunt.progress = 3
    hunt.message = "Поиск объектов (бесплатные карты + DaData)"
    db.commit()
    if settings.demo_mode:
        object_provider = DemoObjectProvider()
        cadastre_provider = DemoCadastreProvider()
        company_provider = DemoCompanyProvider()
        contact_provider = DemoContactProvider()
        owner_provider = None
        hunt.message = "DEMO_MODE=1 — моки (не для продаж)"
        db.commit()
    else:
        # Free maps first (Yandex/2GIS HTML/Nominatim). API keys optional, not required.
        object_provider = FreeMapsObjectProvider()
        cadastre_provider = (
            HttpCadastreProvider() if settings.cadastre_api_url else FreeCadastreProvider()
        )
        company_provider = DaDataCompanyProvider()
        contact_provider = PublicPersonContactEnricher()
        owner_provider = FreeOwnerProvider()
    try:
        pool_count = (
            hunt.requested_count
            if settings.demo_mode
            else min(max(hunt.requested_count * 4, hunt.requested_count + 8), 30)
        )
        objects = await _search_objects_resilient(
            object_provider, hunt.city, hunt.query, pool_count
        )
    except Exception as exc:
        objects = [
            ObjectCandidate(
                external_id=f"provider-error-{hunt.id}",
                name=f"{hunt.query.strip()} — источник временно недоступен",
                address=hunt.city.strip(),
                category="needs_review",
                source_url=_map_search_url(hunt.city, hunt.query),
                source_provider=f"provider-error:{str(exc)[:80]}",
            )
        ]
    if not objects:
        objects = [
            ObjectCandidate(
                external_id=f"empty-{hunt.id}",
                name=f"{hunt.query.strip()} — кандидат на проверку",
                address=hunt.city.strip(),
                category="needs_review",
                source_url=_map_search_url(hunt.city, hunt.query),
                source_provider="needs-review",
            )
        ]
    total = max(len(objects), 1)

    async def company_fetcher(inn):
        return await company_provider.by_inn(inn)

    for idx, candidate in enumerate(objects):
        hunt.message = f"Объект {idx + 1}/{len(objects)}: фото, кадастр, юрлицо"
        hunt.progress = 10 + int((idx / total) * 75)
        db.commit()
        try:
            visual = await asyncio.wait_for(
                VisualEvidenceProvider().enrich(
                    name=candidate.name,
                    address=candidate.address,
                    lat=candidate.lat,
                    lon=candidate.lon,
                    existing_photo_url=candidate.photo_url,
                    existing_source_url=candidate.source_url,
                ),
                timeout=14.0,
            )
            if candidate.lat is None:
                candidate.lat = visual.panorama_lat
            if candidate.lon is None:
                candidate.lon = visual.panorama_lon
            if not candidate.photo_url and visual.photo_url:
                candidate.photo_url = visual.photo_url
        except Exception:
            pass
        obj = _upsert_object(db, candidate)

        cad = None
        try:
            cad = await asyncio.wait_for(cadastre_provider.resolve(candidate), timeout=22.0)
        except Exception as exc:
            obj.cadastre_status = "provider_error"
            obj.cadastre_source = str(exc)[:500]

        owner_inn = ""
        relation = "object_only"
        confidence = 40

        if cad and cad.cadastral_number:
            obj.cadastral_number = cad.cadastral_number
            obj.cadastral_area = cad.area
            obj.cadastral_value = cad.cadastral_value
            obj.cadastre_status = "matched"
            obj.cadastre_source = cad.source_url or cad.source
            confidence = max(confidence, int(cad.match_confidence or 0))
            if cad.owner_inn:
                owner_inn = cad.owner_inn
                relation = "owner_confirmed"
        elif obj.cadastre_status != "provider_error":
            obj.cadastre_status = "not_found"

        # Classic free path: name/address → List-Org / DaData / web (not cadastral proof).
        if not owner_inn and owner_provider is not None:
            try:
                hit = await asyncio.wait_for(
                    owner_provider.resolve(
                        title=core_title(candidate.name) or candidate.name,
                        address=candidate.address,
                        city=hunt.city,
                        cadastral_number=cad.cadastral_number if cad else "",
                    ),
                    timeout=12.0,
                )
                if hit and hit.inn:
                    owner_inn = hit.inn
                    relation = "legal_entity_match"
                    if hit.source == "dadata-name-match" and cad and cad.cadastral_number:
                        relation = "legal_entity_candidate_after_cadastre"
                    confidence = max(confidence, int(hit.confidence or 50))
                    if not obj.cadastre_source:
                        obj.cadastre_source = f"free-owner:{hit.source}"
            except Exception as exc:
                if not obj.cadastre_source:
                    obj.cadastre_source = ""

        if owner_inn:
            await asyncio.wait_for(
                _attach_company_people(
                    db,
                    owner_inn=owner_inn,
                    company_provider=company_provider,
                    contact_provider=contact_provider,
                    company_fetcher=company_fetcher,
                    city=hunt.city,
                ),
                timeout=45.0,
            )
        elif relation == "object_only" and cad and cad.cadastral_number:
            relation = "owner_not_identified"

        if not db.query(HuntResult).filter(
            HuntResult.hunt_id == hunt.id, HuntResult.object_id == obj.id
        ).first():
            db.add(
                HuntResult(
                    hunt_id=hunt.id,
                    object_id=obj.id,
                    owner_company_inn=owner_inn,
                    relation_status=relation,
                    confidence=confidence,
                )
            )
        db.commit()

    hunt.status = "completed"
    hunt.progress = 100
    if settings.demo_mode:
        hunt.message = "Готово (DEMO — мок-данные)"
    else:
        hunt.message = "Готово (бесплатный путь: карты + юрлицо; кадастр — если ответил)"
    db.commit()
