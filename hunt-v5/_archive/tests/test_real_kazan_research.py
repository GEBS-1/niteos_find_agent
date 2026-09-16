import pytest

from app.providers.real_kazan_fixture import (
    RealKazanObjectProvider,
    RealKazanCadastreProvider,
    RealKazanCompanyProvider,
    RealKazanContactProvider,
)
from app.services.ownership import resolve_ultimate_owners
from app.services.scoring import score_contact
from app.services.verification import verify_object


@pytest.mark.asyncio
async def test_two_real_kazan_objects_pipeline():
    objects = await RealKazanObjectProvider().search(
        "Казань", "производственные объекты", 2
    )
    assert len(objects) == 2

    cadastral = []
    cp = RealKazanCadastreProvider()
    for obj in objects:
        cad = await cp.resolve(obj)
        assert cad is not None
        assert cad.owner_inn == "1600000036"
        assert cad.match_confidence == 100
        cadastral.append(cad)

    assert cadastral[0].cadastral_number == "16:50:000000:10446"
    assert cadastral[0].area == 603.3
    assert cadastral[1].cadastral_number == "16:50:000000:13166"
    assert cadastral[1].area == 2035.9

    company_provider = RealKazanCompanyProvider()
    company = await company_provider.by_inn("1600000036")
    assert company is not None
    assert company.ogrn == "1021603624921"
    assert company.director_name == "Усманов Рустем Ринатович"
    assert company.founders[0].inn == "7736050003"
    assert company.founders[0].share_percent == 100.0

    # This is deliberately empty because the chain reaches a public JSC
    # and we do not invent a natural-person UBO.
    owners = await resolve_ultimate_owners("1600000036", company_provider.by_inn)
    assert owners == []

    contacts = await RealKazanContactProvider().search_person(
        company.director_name, company.name, "Казань", "general_director"
    )
    assert len(contacts) == 1
    score, status = score_contact(contacts[0])
    # Name + company + role + city = 85; no explicit personal contact link.
    assert score == 85
    assert status == "probable"
    assert contacts[0].explicit_person_link is False

    # Real records have no verified object-specific photo/coordinates in our source;
    # verification must show that instead of pretending 100%.
    for obj, cad in zip(objects, cadastral):
        v = verify_object(
            name=obj.name,
            address=obj.address,
            lat=obj.lat,
            lon=obj.lon,
            photo_url=obj.photo_url,
            cadastral_number=cad.cadastral_number,
            cadastre_confidence=cad.match_confidence,
            owner_inn=cad.owner_inn,
            owner_company_found=True,
        )
        assert v["status"] == "probable"
        assert v["score"] == 75
        assert next(c for c in v["checks"] if c["key"] == "photo")["passed"] is False
        assert next(c for c in v["checks"] if c["key"] == "coordinates")["passed"] is False
