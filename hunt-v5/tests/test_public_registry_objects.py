from app.providers.public_registry_objects import PublicRegistryObjectProvider


class _Response:
    status_code = 200
    text = """
    <html><title>Продажа здания гостиницы</title>
    Адрес: Республика Татарстан, г. Казань, ул. Тэцевская, 1.
    Кадастровый номер 16:50:000000:13166.
    Собственник ООО «Газпром трансгаз Казань», ИНН 1600000036.
    </html>
    """


class _Client:
    async def get(self, url, timeout=12.0):
        return _Response()


async def test_public_registry_candidate_requires_cadastre_city_and_query():
    candidate = await PublicRegistryObjectProvider()._candidate_from_url(
        _Client(),
        "Казань",
        "гостиница",
        "https://new.etpgpb.ru/procedures/demo",
    )

    assert candidate is not None
    assert candidate.source_provider == "public-registry-free"
    assert "Казань" in candidate.address
