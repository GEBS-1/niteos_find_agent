from __future__ import annotations


def verify_object(*, name: str, address: str, lat, lon, photo_url: str,
                  cadastral_number: str, cadastre_confidence: int,
                  owner_inn: str, owner_company_found: bool) -> dict:
    """Deterministic object verification. No LLM."""
    checks = []

    def add(key: str, label: str, passed: bool, weight: int, detail: str = ""):
        checks.append({
            "key": key,
            "label": label,
            "passed": bool(passed),
            "weight": weight,
            "detail": detail,
        })

    add("name", "Название объекта", bool((name or "").strip()), 5, name or "Не найдено")
    add("address", "Адрес", bool((address or "").strip()), 15, address or "Не найдено")
    add("coordinates", "Координаты", lat is not None and lon is not None, 15,
        f"{lat}, {lon}" if lat is not None and lon is not None else "Не найдены")
    add("photo", "Фотография объекта", bool((photo_url or "").strip()), 10,
        photo_url or "Фото не найдено")
    add("cadastre", "Кадастровый объект", bool((cadastral_number or "").strip()), 25,
        cadastral_number or "Не найден")
    add("cadastre_match", "Совпадение здания с кадастром", int(cadastre_confidence or 0) >= 70, 10,
        f"{int(cadastre_confidence or 0)}%")
    add("owner_inn", "ИНН правообладателя", bool((owner_inn or "").strip()), 10,
        owner_inn or "Не найден")
    add("company", "Компания по ИНН", bool(owner_company_found), 10,
        "Подтверждена" if owner_company_found else "Не подтверждена")

    score = sum(c["weight"] for c in checks if c["passed"])
    if score >= 90:
        status = "verified"
    elif score >= 70:
        status = "probable"
    else:
        status = "needs_review"

    return {"score": score, "status": status, "checks": checks}
