from app.providers.public_search import SearchHit
from app.services.contact_enrichment import PublicPersonContactEnricher


class FakeSearch:
    async def search(self, query: str, limit: int = 10):
        if "главный инженер" in query.lower() or "чучкалов" in query.lower():
            return [
                SearchHit(
                    title="Чучкалов Михаил Владимирович – Татцентр",
                    url="https://tatcenter.ru/person/chuchkalov-mihail-vladimirovich/",
                    snippet=(
                        "Чучкалов Михаил Владимирович. Главный инженер — первый заместитель "
                        "генерального директора ООО «Газпром трансгаз Казань». "
                        "Телефон: +7 (843) 288-22-30. Электронная почта: info@tattg.gazprom.ru. "
                        "Адрес: Казань."
                    ),
                    source="fake",
                )
            ]
        return []


class FakeSocialSearch:
    async def search(self, query: str, limit: int = 10):
        if "site:vk.com" in query.lower() or "vk" in query.lower():
            return [
                SearchHit(
                    title="Иванов Сергей Петрович | ВКонтакте",
                    url="https://vk.com/ivanov_sergey_test",
                    snippet="Иванов Сергей Петрович. Казань. ООО Альфа Инвест.",
                    source="fake",
                )
            ]
        return []


async def test_role_people_and_contacts_from_public_profile():
    enricher = PublicPersonContactEnricher(search=FakeSearch())

    people = await enricher.search_role_people("ООО Газпром трансгаз Казань", "Казань", limit=3)
    assert any(p["full_name"] == "Чучкалов Михаил Владимирович" for p in people)

    contacts = await enricher.search_person(
        "Чучкалов Михаил Владимирович",
        "ООО Газпром трансгаз Казань",
        "Казань",
        "chief_engineer",
    )
    assert any(c.contact_type == "phone" and c.value for c in contacts)
    assert any(c.contact_type == "email" and c.value == "info@tattg.gazprom.ru" for c in contacts)


async def test_social_profile_url_becomes_contact_route():
    enricher = PublicPersonContactEnricher(search=FakeSocialSearch())

    contacts = await enricher.search_person(
        "Иванов Сергей Петрович",
        "ООО Альфа Инвест",
        "Казань",
        "general_director",
    )

    assert any(c.contact_type == "vk" and c.value == "https://vk.com/ivanov_sergey_test" for c in contacts)
