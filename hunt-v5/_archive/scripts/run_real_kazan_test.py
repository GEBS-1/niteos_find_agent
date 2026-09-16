import asyncio, json
from app.providers.real_kazan_fixture import (
    RealKazanObjectProvider, RealKazanCadastreProvider, RealKazanCompanyProvider,
    RealKazanContactProvider, AUCTION_SOURCE, COMPANY_SOURCE, MANAGEMENT_SOURCE
)
from app.services.scoring import score_contact
from app.services.verification import verify_object

async def main():
    op = RealKazanObjectProvider()
    cp = RealKazanCadastreProvider()
    companies = RealKazanCompanyProvider()
    contacts_provider = RealKazanContactProvider()

    rows = []
    for obj in await op.search("Казань", "производственный объект", 2):
        cad = await cp.resolve(obj)
        company = await companies.by_inn(cad.owner_inn)
        contact_rows = []
        if company.director_name:
            for c in await contacts_provider.search_person(
                company.director_name, company.name, "Казань", "general_director"
            ):
                score, status = score_contact(c)
                contact_rows.append({
                    "type": c.contact_type,
                    "value": c.value,
                    "score": score,
                    "status": status,
                    "explicit_person_link": c.explicit_person_link,
                    "source": c.source_url,
                })

        verification = verify_object(
            name=obj.name, address=obj.address, lat=obj.lat, lon=obj.lon,
            photo_url=obj.photo_url, cadastral_number=cad.cadastral_number,
            cadastre_confidence=cad.match_confidence, owner_inn=cad.owner_inn,
            owner_company_found=company is not None,
        )
        rows.append({
            "object": {
                "name": obj.name,
                "address": obj.address,
                "cadastral_number": cad.cadastral_number,
                "area_m2": cad.area,
                "object_source": obj.source_url,
            },
            "owner": {
                "name": cad.owner_name,
                "inn": cad.owner_inn,
                "ogrn": cad.owner_ogrn,
                "source": cad.source_url,
                "evidence": cad.source,
            },
            "company": {
                "name": company.name,
                "director": company.director_name,
                "founder": company.founders[0].name,
                "founder_inn": company.founders[0].inn,
                "founder_share": company.founders[0].share_percent,
                "revenue_2024": company.revenue,
                "profit_2024": company.profit,
                "source": company.source_url,
            },
            "contacts": contact_rows,
            "verification": verification,
        })

    print(json.dumps({
        "city": "Казань",
        "query": "производственный объект",
        "mode": "real_public_sources",
        "objects": rows,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
