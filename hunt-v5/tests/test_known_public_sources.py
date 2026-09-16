from app.providers.known_public_sources import (
    known_public_cadastre,
    known_public_object_candidates,
    known_public_object_contacts,
    known_public_owner,
)


def test_known_public_source_returns_kazan_warehouse_with_owner_inn():
    rows = known_public_object_candidates("Казань", "складской комплекс", 1)

    assert len(rows) == 1
    assert rows[0].source_provider == "known-public-source"
    cad = known_public_cadastre(rows[0])
    assert cad is not None
    assert cad.cadastral_number == "16:50:000000:13166"
    assert cad.owner_inn == "1600000036"


def test_known_public_hotel_owner_and_contacts():
    rows = known_public_object_candidates("Казань", "отель", 1)

    assert len(rows) == 1
    assert rows[0].name == "Cosmos Kazan Hotel"
    assert known_public_cadastre(rows[0]) is None

    owner = known_public_owner(rows[0].name, rows[0].address, "Казань")
    contacts = known_public_object_contacts(rows[0].name, rows[0].address, owner["inn"])

    assert owner["inn"] == "7725642985"
    assert any(x["contact_type"] == "phone" for x in contacts)
