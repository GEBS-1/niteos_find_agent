from app.providers.kazankompressormash_research import card


def test_real_card_has_no_fake_cadastre_or_owner():
    c = card()
    assert c["object"]["address"].endswith("Халитова, 1")
    assert c["object"]["photo"]["status"] == "confirmed_visual"
    assert c["object"]["cadastre"]["exact_facade_cadastral_number"] is None
    assert c["verification"]["checks"]["building_owner_from_egrn"] is False


def test_real_card_prioritizes_chief_engineer_and_keeps_person_contact_separate():
    c = card()
    assert c["recommended_route"]["primary"] == "Бакиров Альберт Асхатович"
    sagdiev = next(x for x in c["decision_makers"] if x["full_name"] == "Сагдиев Ильнур Ильдарович")
    assert sagdiev["contacts"][0]["value"] == "+7 (843) 291-79-21"
    assert sagdiev["contacts"][0]["status"] == "confirmed"
    bakirov = next(x for x in c["decision_makers"] if x["full_name"] == "Бакиров Альберт Асхатович")
    assert bakirov["contacts"] == []
    assert bakirov["contact_status"] == "direct_public_contact_not_found"
