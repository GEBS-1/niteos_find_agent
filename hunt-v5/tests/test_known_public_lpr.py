from app.providers.known_public_lpr import known_lpr_contacts, known_lpr_people
from app.services.scoring import score_contact


def test_known_public_lpr_has_actionable_contacts():
    people = known_lpr_people("1600000036")

    assert people
    assert people[0]["full_name"] == "Чучкалов Михаил Владимирович"
    contacts = known_lpr_contacts(people[0])
    assert contacts
    assert all(score_contact(c)[1] == "confirmed" for c in contacts)


def test_known_public_lpr_can_be_contactless_candidate():
    people = known_lpr_people("7725642985")

    assert people
    assert people[0]["full_name"] == "Терехов Константин Михайлович"
    assert people[0]["role"] == "ultimate_identified_owner"
    assert known_lpr_contacts(people[0]) == []
