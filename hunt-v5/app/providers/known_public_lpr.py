from __future__ import annotations

from app.providers.base import ContactCandidate


_PEOPLE = {
    "1600000036": [
        {
            "full_name": "Чучкалов Михаил Владимирович",
            "role": "chief_engineer",
            "source": "https://tatcenter.ru/person/chuchkalov-mihail-vladimirovich/",
            "contacts": [
                {
                    "contact_type": "phone",
                    "value": "+7 (843) 288-22-30",
                    "source_url": "https://tatcenter.ru/person/chuchkalov-mihail-vladimirovich/",
                    "source_type": "public_person_profile",
                },
                {
                    "contact_type": "email",
                    "value": "info@tattg.gazprom.ru",
                    "source_url": "https://tatcenter.ru/person/chuchkalov-mihail-vladimirovich/",
                    "source_type": "public_person_profile",
                },
            ],
        }
    ],
    "7725642985": [
        {
            "full_name": "Терехов Константин Михайлович",
            "role": "ultimate_identified_owner",
            "source": "https://hotgrade.ru/hotel/kazan/cosmos-kazan-hotel-otel-kosmos-kazan",
            "contacts": [],
        }
    ]
}


def known_lpr_people(company_inn: str) -> list[dict]:
    return list(_PEOPLE.get(company_inn, []))


def known_lpr_contacts(person: dict) -> list[ContactCandidate]:
    out: list[ContactCandidate] = []
    for item in person.get("contacts") or []:
        out.append(
            ContactCandidate(
                contact_type=item["contact_type"],
                value=item["value"],
                source_url=item["source_url"],
                source_type=item["source_type"],
                name_match=True,
                company_match=True,
                role_match=True,
                city_match=True,
                explicit_person_link=True,
            )
        )
    return out
