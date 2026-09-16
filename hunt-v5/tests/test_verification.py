from app.services.verification import verify_object


def test_verified_object():
    result = verify_object(
        name="Завод Альфа",
        address="Казань, ул. Промышленная, 10",
        lat=55.78,
        lon=49.12,
        photo_url="/static/demo-factory.svg",
        cadastral_number="16:50:0101:1234",
        cadastre_confidence=98,
        owner_inn="1650123456",
        owner_company_found=True,
    )
    assert result["score"] == 100
    assert result["status"] == "verified"
    assert all(c["passed"] for c in result["checks"])


def test_missing_photo_is_visible():
    result = verify_object(
        name="Объект",
        address="Казань",
        lat=55.78,
        lon=49.12,
        photo_url="",
        cadastral_number="16:50:0101:1234",
        cadastre_confidence=95,
        owner_inn="1650123456",
        owner_company_found=True,
    )
    assert result["score"] == 90
    photo = next(c for c in result["checks"] if c["key"] == "photo")
    assert photo["passed"] is False
