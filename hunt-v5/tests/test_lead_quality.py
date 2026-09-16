from app.services.lead_quality import lead_quality


def test_owner_without_person_contact_is_working_owner_card():
    quality = lead_quality(
        obj={"name": "БЦ Пример", "address": "Москва, ул. Примерная, 1", "photo_url": "https://img.example/facade.jpg"},
        company={"inn": "7700000000", "name": "ООО Владелец"},
        people=[],
        confidence=82,
    )

    assert quality["status"] == "ready_owner_only"
    assert quality["owner_ok"] is True
    assert quality["person_contact_ok"] is False
    assert "нет публичного контакта конкретного ЛПР/владельца" in quality["warnings"]


def test_no_owner_is_not_a_ready_card_even_with_photo():
    quality = lead_quality(
        obj={"name": "БЦ Пример", "address": "Москва, ул. Примерная, 1", "photo_url": "https://img.example/facade.jpg"},
        company=None,
        people=[],
        confidence=80,
    )

    assert quality["status"] == "needs_owner"
    assert "владелец/юрлицо здания не подтверждено" in quality["reasons"]
