from app.providers.torgi_gov import TorgiGovCadastreProvider, TorgiGovProvider


def test_torgi_candidate_from_nested_lot_json():
    item = {
        "id": "22000000000000000001_1",
        "lotName": "Продажа здания склада",
        "estateAddress": "Республика Татарстан, г. Казань, ул. Тэцевская, 1",
        "characteristics": [{"name": "Кадастровый номер", "value": "16:50:000000:13166"}],
    }

    candidate = TorgiGovProvider()._candidate_from_item("Казань", "складской комплекс", item)

    assert candidate is not None
    assert candidate.source_provider == "torgi-gov-api"
    assert "22000000000000000001_1" in candidate.source_url


def test_torgi_cadastre_extracts_owner_inn_from_detail():
    data = {
        "id": "22000000000000000001_1",
        "lotName": "Продажа здания склада",
        "estateAddress": "Республика Татарстан, г. Казань, ул. Тэцевская, 1",
        "text": (
            "Кадастровый номер 16:50:000000:13166. "
            "Продавец собственник ООО «Газпром трансгаз Казань», ИНН 1600000036."
        ),
    }
    obj = TorgiGovProvider()._candidate_from_item("Казань", "складской комплекс", data)

    cad = TorgiGovCadastreProvider()._cadastre_from_detail(obj, "22000000000000000001_1", data)

    assert cad is not None
    assert cad.cadastral_number == "16:50:000000:13166"
    assert cad.owner_inn == "1600000036"
