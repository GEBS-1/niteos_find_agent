import pytest

from app.providers.base import ObjectCandidate
from app.services.hunt import _search_objects_resilient


class FakeObjectProvider:
    def __init__(self):
        self.calls = []

    async def search(self, city: str, query: str, count: int):
        self.calls.append((city, query, count))
        if query == "отель" and city == "Казань":
            return [
                ObjectCandidate(
                    external_id="hotel-kazan",
                    name="Гостиница Казань",
                    address="Казань, ул. Тестовая, 1",
                    source_url="https://example.test/hotel-kazan",
                    source_provider="fake",
                )
            ]
        if query == "складской комплекс" and city == "Самара":
            return [
                ObjectCandidate(
                    external_id="warehouse-samara",
                    name="Складской комплекс Самара",
                    address="Самара, ул. Складская, 1",
                    source_url="https://example.test/warehouse-samara",
                    source_provider="fake",
                )
            ]
        return []


@pytest.mark.asyncio
async def test_region_scope_fallback_searches_region_cities():
    provider = FakeObjectProvider()

    rows = await _search_objects_resilient(
        provider,
        city="Республика Татарстан",
        query="неизвестный тип",
        count=3,
    )

    assert rows[0].name == "Гостиница Казань"
    assert ("Казань", "отель", 3) in provider.calls
    assert not any(call[0] == "Республика Татарстан" and call[1] == "отель" for call in provider.calls)


@pytest.mark.asyncio
async def test_multi_city_scope_splits_selected_cities():
    provider = FakeObjectProvider()

    await _search_objects_resilient(
        provider,
        city="Казань, Самара",
        query="бизнес центр",
        count=2,
    )

    called_cities = [city for city, _query, _count in provider.calls]
    assert "Казань" in called_cities
    assert "Самара" in called_cities
    assert "Казань, Самара" not in called_cities


@pytest.mark.asyncio
async def test_multi_building_type_scope_splits_selected_types():
    provider = FakeObjectProvider()

    rows = await _search_objects_resilient(
        provider,
        city="Казань, Самара",
        query="отель, складской комплекс",
        count=2,
    )

    names = {row.name for row in rows}
    assert "Гостиница Казань" in names
    assert "Складской комплекс Самара" in names
