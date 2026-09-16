import pytest
from app.providers.visual import VisualEvidenceProvider


@pytest.mark.asyncio
async def test_visual_keeps_sourced_photo_and_coordinates():
    v = await VisualEvidenceProvider().enrich(
        name="Завод", address="Казань", lat=55.8, lon=49.1,
        existing_photo_url="https://example.org/facade.jpg",
        existing_source_url="https://example.org/article",
    )
    assert v.photo_url.endswith("facade.jpg")
    assert v.photo_source_url.endswith("article")
    assert v.map_url.startswith("https://yandex.ru/maps/")
    assert v.confidence >= 80
