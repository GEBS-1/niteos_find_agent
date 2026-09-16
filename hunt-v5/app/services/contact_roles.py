ROLE_PRIORITY = {
    "chief_engineer": 100,
    "technical_director": 95,
    "chief_power_engineer": 93,
    "facility_director": 90,
    "operations_director": 88,
    "general_director": 75,
    "ultimate_identified_owner": 65,
}

ROLE_LABELS_RU = {
    "chief_engineer": "Главный инженер",
    "technical_director": "Технический директор",
    "chief_power_engineer": "Главный энергетик",
    "facility_director": "Директор по эксплуатации",
    "operations_director": "Директор по производству",
    "general_director": "Генеральный директор",
    "ultimate_identified_owner": "Конечный установленный владелец",
}


def rank_people(people: list[dict]) -> list[dict]:
    return sorted(people, key=lambda p: ROLE_PRIORITY.get(p.get("role", ""), 0), reverse=True)
