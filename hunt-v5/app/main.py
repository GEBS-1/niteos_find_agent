from pathlib import Path
import asyncio
from urllib.parse import quote

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_db, SessionLocal
from app.models import Hunt, HuntResult, ObjectEntity, Company, Person, Contact, OwnershipEdge
from app.schemas import HuntCreate
from app.services.hunt import run_hunt
from app.services.verification import verify_object
from app.services.llm import OpenAIProposalEngine
from app.providers.visual import VisualEvidenceProvider
from app.services.contact_roles import rank_people
from app.services.sales_card import actionable_people, lighting_score
from app.services.lead_quality import lead_quality
from app.services.ai_router import current_ai_plan, factual_tasks
from app.providers.known_public_finance import known_public_finance
from app.providers.known_public_sources import known_public_object_contacts

Base.metadata.create_all(bind=engine)
app = FastAPI(title=settings.app_name, version="5.0.0")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "demo_mode": settings.demo_mode, "llm_enabled": settings.llm_enabled}


@app.get("/api/providers")
def providers():
    """Primary path is free (no Maps API keys). Demo only if DEMO_MODE=1."""
    if settings.demo_mode:
        return {"demo_mode": True, "object": "demo", "note": "DEMO_MODE=1 — моки"}
    return {
        "demo_mode": False,
        "path": "free",
        "object": "torgi_gov_api+2gis_api+yandex_maps+2gis_html+nominatim",
        "visual": "yandex_org_photo+yandex_images+nominatim",
        "owner": "dadata+list-org+web",
        "contact": "public_search_normalized+llm_query_planner",
        "company": "dadata" if settings.dadata_api_key else "not_configured",
        "cadastre": "http" if settings.cadastre_api_url else "torgi_gov_api+nspd_soft+free_web",
        "llm": "disabled" if not settings.llm_enabled else (
            "routerai" if (settings.routerai_api_key or settings.router_api_key) else "openai"
        ),
        "keys": {
            "dadata": bool(settings.dadata_api_key),
            "routerai": bool(settings.routerai_api_key or settings.router_api_key),
            # optional / archived API providers — not required for hunt
            "twogis_api": bool(settings.twogis_api_key),
            "yandex_maps_api": bool(settings.yandex_maps_api_key),
            "cadastre_http": bool(settings.cadastre_api_url),
        },
    }


def _bg(hunt_id: int):
    db = SessionLocal()
    try:
        h = db.get(Hunt, hunt_id)
        if h:
            asyncio.run(run_hunt(db, h))
    finally:
        db.close()


def _company_finance(c: Company | None) -> dict:
    if not c:
        return {
            "status": "no_company",
            "summary": "Финансы появятся после подтверждения ИНН владельца.",
            "source": "",
            "links": [],
        }
    links = [
        {
            "label": "Rusprofile",
            "url": f"https://www.rusprofile.ru/search?query={quote(c.inn)}",
        },
        {
            "label": "Checko",
            "url": f"https://checko.ru/search?query={quote(c.inn)}",
        },
        {
            "label": "List-Org",
            "url": f"https://www.list-org.com/search?type=all&val={quote(c.inn)}",
        },
        {
            "label": "РБК Компании",
            "url": f"https://companies.rbc.ru/search/?query={quote(c.inn)}",
        },
    ]
    known = known_public_finance(c.inn)
    if known:
        return {
            "status": "found",
            "summary": known["summary"],
            "source": known["source"],
            "period": known["period"],
            "revenue": known["revenue"],
            "profit": known["profit"],
            "employees": known["employees"],
            "links": links,
        }
    has_any = any(x is not None for x in (c.revenue, c.profit, c.employees))
    if has_any:
        summary = "Финансовые показатели получены из провайдера компании; проверьте первоисточники по ссылкам."
        status = "found"
    else:
        summary = (
            "DaData подтвердила юрлицо, но не вернула выручку, прибыль или сотрудников. "
            "Так бывает из-за тарифа/доступности данных или отсутствия раскрытых показателей у источника; "
            "проверка вынесена в открытые профили по ИНН."
        )
        status = "not_returned"
    return {
        "status": status,
        "summary": summary,
        "source": c.source,
        "revenue": c.revenue,
        "profit": c.profit,
        "employees": c.employees,
        "links": links,
    }


def _contact_scope(contact: Contact) -> str:
    if "personal_mobile" in (contact.source_type or ""):
        return "personal"
    if contact.explicit_person_link or contact.is_direct_person_contact:
        return "public_work_contact"
    return "public_contact"


def _contact_research_links(company: Company | None, people: list[dict]) -> list[dict]:
    links: list[dict] = []
    if not company:
        return links
    for person in people[:5]:
        name = person.get("full_name") or ""
        role_name = person.get("role") or ""
        if not name:
            continue
        for label, suffix in (
            ("Телефон ЛПР", "телефон"),
            ("Мобильный/WhatsApp", "мобильный whatsapp"),
            ("Email ЛПР", "email почта"),
            ("VK", "site:vk.com"),
            ("Одноклассники", "site:ok.ru"),
            ("Instagram", "site:instagram.com"),
            ("Telegram", "site:t.me telegram"),
            ("TenChat", "site:tenchat.ru"),
            ("MAX", "site:max.ru max мессенджер"),
        ):
            links.append({
                "label": f"{label}: {name}",
                "url": f"https://yandex.ru/search/?text={quote(f'{name} {company.name} {role_name} {suffix}'.strip())}",
            })
    links.append({
        "label": "Контакты компании по ИНН",
        "url": f"https://yandex.ru/search/?text={quote(f'{company.inn} {company.name} контакты телефон email'.strip())}",
    })
    return links[:12]


def _object_contacts(o: ObjectEntity, c: Company | None) -> list[dict]:
    return [
        {
            "type": item.get("contact_type"),
            "value": item.get("value"),
            "label": item.get("label") or "публичный контакт объекта",
            "source_url": item.get("source_url"),
            "contact_scope": "public_object_contact",
        }
        for item in known_public_object_contacts(o.name, o.address, c.inn if c else "")
    ]


@app.post("/api/hunts")
def create_hunt(payload: HuntCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    h = Hunt(
        city=payload.city.strip(),
        query=payload.query.strip(),
        requested_count=payload.count,
        status="queued",
        progress=0,
        message="В очереди",
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    background.add_task(_bg, h.id)
    return {"id": h.id, "status": h.status}


@app.get("/api/hunts/{hunt_id}")
def get_hunt(hunt_id: int, db: Session = Depends(get_db)):
    h = db.get(Hunt, hunt_id)
    if not h:
        raise HTTPException(404, "hunt not found")
    return {
        "id": h.id,
        "city": h.city,
        "query": h.query,
        "requested_count": h.requested_count,
        "status": h.status,
        "progress": h.progress,
        "message": h.message,
        "created_at": h.created_at.isoformat(),
    }


def serialize_result(db: Session, hr: HuntResult):
    o = db.get(ObjectEntity, hr.object_id)
    c = db.query(Company).filter(Company.inn == hr.owner_company_inn).first() if hr.owner_company_inn else None

    people = []
    if c:
        for p in db.query(Person).filter(Person.company_inn == c.inn).all():
            cs = (
                db.query(Contact)
                .filter(Contact.person_id == p.id, Contact.status.in_(["confirmed", "probable"]))
                .order_by(Contact.confidence.desc())
                .all()
            )
            people.append({
                "id": p.id,
                "full_name": p.full_name,
                "role": p.role,
                "effective_share": p.effective_share,
                "source": p.source,
                "contacts": [
                    {
                        "type": x.contact_type,
                        "value": x.value,
                        "confidence": x.confidence,
                        "status": x.status,
                        "source_url": x.source_url,
                        "source_type": x.source_type,
                        "direct": x.is_direct_person_contact,
                        "contact_scope": _contact_scope(x),
                    }
                    for x in cs
                ],
            })

    edges = []
    if c:
        edges = [
            {
                "from_company_inn": e.from_company_inn,
                "to_kind": e.to_kind,
                "to_name": e.to_name,
                "to_company_inn": e.to_company_inn,
                "share_percent": e.share_percent,
                "source": e.source,
            }
            for e in db.query(OwnershipEdge).filter(OwnershipEdge.from_company_inn == c.inn).all()
        ]

    verification = verify_object(
        name=o.name,
        address=o.address,
        lat=o.lat,
        lon=o.lon,
        photo_url=o.photo_url,
        cadastral_number=o.cadastral_number,
        cadastre_confidence=hr.confidence if o.cadastral_number else 0,
        owner_inn=hr.owner_company_inn,
        owner_company_found=c is not None,
    )

    ranked_people = rank_people(people)
    visible_people = (
        actionable_people(ranked_people)
        if settings.sales_hide_people_without_contacts
        else ranked_people
    )
    map_url = ""
    if o.lat is not None and o.lon is not None:
        map_url = (
            "https://yandex.ru/maps/?ll="
            f"{o.lon:.6f}%2C{o.lat:.6f}&z=17&l=map%2Cstv"
        )
    elif o.address or o.name:
        map_url = f"https://yandex.ru/maps/?text={quote(f'{o.name} {o.address}'.strip())}"
    lighting = lighting_score(
        photo_url=o.photo_url,
        panorama_url=map_url,
        road_visible=bool(o.lat is not None and o.lon is not None),
        facade_area_signal=bool(o.photo_url),
        entrance_signal=bool(o.photo_url),
        architectural_rhythm_signal=bool(o.photo_url),
        signage_signal=bool(o.name),
    )

    object_payload = {
        "id": o.id,
        "name": o.name,
        "address": o.address,
        "lat": o.lat,
        "lon": o.lon,
        "category": o.category,
        "photo_url": o.photo_url,
        "source_url": o.source_url,
        "map_url": map_url,
        "source_provider": o.source_provider,
        "cadastral_number": o.cadastral_number,
        "cadastral_area": o.cadastral_area,
        "cadastral_value": o.cadastral_value,
        "cadastre_status": o.cadastre_status,
        "cadastre_source": o.cadastre_source if o.cadastral_number else "",
    }
    company_payload = None if not c else {
        "inn": c.inn,
        "ogrn": c.ogrn,
        "name": c.name,
        "legal_address": c.legal_address,
        "status": c.status,
        "revenue": c.revenue,
        "profit": c.profit,
        "employees": c.employees,
        "source": c.source,
        "finance": _company_finance(c),
    }
    quality = lead_quality(
        obj=object_payload,
        company=company_payload,
        people=visible_people,
        confidence=hr.confidence,
    )

    return {
        "id": hr.id,
        "relation_status": hr.relation_status,
        "confidence": hr.confidence,
        "lead_quality": quality,
        "verification": verification,
        "lighting": lighting,
        "contact_audit": {
            "actionable_people": len(visible_people),
            "people_candidates": len(ranked_people),
            "rule": "целевые контакты показываются отдельно; кандидаты ЛПР и маршруты поиска не скрываются",
        },
        "owner_research": [
            {
                "label": "Поиск владельца по объекту",
                "url": f"https://yandex.ru/search/?text={quote(f'{o.name} {o.address} владелец ИНН'.strip())}",
            },
            {
                "label": "Поиск в List-Org",
                "url": f"https://www.list-org.com/search?type=all&val={quote((o.name or '').strip())}",
            },
        ],
        "object": object_payload,
        "company": company_payload,
        "finance": _company_finance(c),
        "ownership_edges": edges,
        "people": visible_people,
        "people_candidates": ranked_people,
        "object_contacts": _object_contacts(o, c),
        "contact_research": _contact_research_links(c, ranked_people),
    }




@app.get("/api/objects/{object_id}/visual")
def object_visual(object_id: int, db: Session = Depends(get_db)):
    o = db.get(ObjectEntity, object_id)
    if not o:
        raise HTTPException(404, "object not found")
    async def _run():
        return await VisualEvidenceProvider().enrich(
            name=o.name, address=o.address, lat=o.lat, lon=o.lon,
            existing_photo_url=o.photo_url, existing_source_url=o.source_url,
        )
    v = asyncio.run(_run())
    return v.__dict__


@app.post("/api/objects/{object_id}/proposal")
def object_proposal(object_id: int, db: Session = Depends(get_db)):
    o = db.get(ObjectEntity, object_id)
    if not o:
        raise HTTPException(404, "object not found")
    hr = db.query(HuntResult).filter(HuntResult.object_id == object_id).order_by(HuntResult.id.desc()).first()
    if not hr:
        raise HTTPException(404, "object has no hunt result")
    card = serialize_result(db, hr)
    async def _run():
        visual = await VisualEvidenceProvider().enrich(
            name=o.name, address=o.address, lat=o.lat, lon=o.lon,
            existing_photo_url=o.photo_url, existing_source_url=o.source_url,
        )
        return await OpenAIProposalEngine().build(card=card, photo_url=visual.photo_url)
    return asyncio.run(_run())


@app.get("/api/public-config")
def public_config():
    return {
        # Public Yandex Maps links work without API key; key only for JS SDK if used later.
        "yandex_maps_api_key": settings.yandex_maps_api_key,
        "panorama_enabled": True,
        "openai_model": settings.llm_model if settings.llm_enabled else "disabled",
    }

@app.get("/api/hunts/{hunt_id}/results")
def results(hunt_id: int, db: Session = Depends(get_db)):
    if not db.get(Hunt, hunt_id):
        raise HTTPException(404, "hunt not found")
    return [serialize_result(db, r) for r in db.query(HuntResult).filter(HuntResult.hunt_id == hunt_id).all()]




@app.get("/api/system-design")
def system_design():
    return {
        "primary_path": "free",
        "pipeline": [
            "free_maps_search",
            "visual_evidence",
            "nspd_or_http_cadastre_soft",
            "free_web_cadastre_sources",
            "free_legal_entity_match",
            "company_enrichment",
            "ownership_graph",
            "decision_makers",
            "sales_card",
            "optional_llm_proposal",
        ],
        "hard_rule": "NO_SOURCE = NO_FACT",
        "sales_rule": "NO_ACTIONABLE_CONTACT = HIDE_PERSON",
        "archived": "_archive/ (2GIS API, research fixtures, demo smoke pages)",
        "ai": [x.__dict__ for x in current_ai_plan()],
        "deterministic_tasks": factual_tasks(),
    }
