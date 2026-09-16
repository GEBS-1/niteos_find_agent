from app.providers.base import ObjectCandidate
from app.providers.free_cadastre_web import FreeCadastreWebProvider


def test_rejects_generic_city_page_cadastre_number():
    obj = ObjectCandidate(
        external_id="x",
        name="Cosmos Kazan",
        address="улица Лесгафта, 7",
    )
    text = (
        "Казань каталог объектов. Кадастровый номер 16:16:000000:4003. "
        "Другие районы и справочная информация."
    )
    assert FreeCadastreWebProvider()._record_from_text(
        obj, "https://example.org/kazan", text
    ) is None


def test_accepts_cadastre_when_address_and_owner_are_near():
    obj = ObjectCandidate(
        external_id="x",
        name="Здание склада с пристроем",
        address="Республика Татарстан, г. Казань, ул. Тэцевская, 1",
    )
    text = (
        "Продажа недвижимого имущества: Здание склада с пристроем, "
        "адрес Республика Татарстан, г. Казань, ул. Тэцевская, 1. "
        "Кадастровый номер 16:50:000000:13166, площадь 2035,9 кв. м. "
        "Продавец собственник ООО «Газпром трансгаз Казань», ИНН 1600000036."
    )
    cad = FreeCadastreWebProvider()._record_from_text(
        obj, "https://new.etpgpb.ru/procedures/demo", text
    )
    assert cad is not None
    assert cad.cadastral_number == "16:50:000000:13166"
    assert cad.owner_inn == "1600000036"
    assert cad.area == 2035.9


async def test_resolve_checks_object_source_before_search():
    obj = ObjectCandidate(
        external_id="x",
        name="Здание склада с пристроем",
        address="Республика Татарстан, г. Казань, ул. Тэцевская, 1",
        source_url="https://new.etpgpb.ru/procedures/demo",
    )
    provider = FreeCadastreWebProvider()
    calls = []

    async def fake_from_url(client, candidate, url):
        calls.append(url)
        assert candidate is obj
        return provider._record_from_text(
            obj,
            url,
            "Здание склада с пристроем, адрес Республика Татарстан, г. Казань, "
            "ул. Тэцевская, 1. Кадастровый номер 16:50:000000:13166. "
            "Собственник ООО «Газпром трансгаз Казань», ИНН 1600000036.",
        )

    provider._from_url = fake_from_url
    cad = await provider.resolve(obj)

    assert cad is not None
    assert cad.owner_inn == "1600000036"
    assert calls == [obj.source_url]
