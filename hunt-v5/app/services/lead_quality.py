from __future__ import annotations

import re


BAD_PHOTO_RE = re.compile(
    r"logo|icon|sprite|avatar|placeholder|blank|1x1|inside|interior|menu|food|dish|banner",
    re.I,
)


def has_probable_exterior_photo(obj: dict) -> bool:
    url = str(obj.get("photo_url") or "")
    return bool(url and not BAD_PHOTO_RE.search(url))


def has_person_contact(people: list[dict]) -> bool:
    direct_types = {
        "phone",
        "email",
        "telegram",
        "vk",
        "ok",
        "instagram",
        "tenchat",
        "whatsapp",
        "max",
        "profile",
        "professional_profile",
    }
    for person in people or []:
        for contact in person.get("contacts") or []:
            if contact.get("status") not in {"confirmed", "probable"}:
                continue
            if contact.get("type") not in direct_types:
                continue
            if str(contact.get("value") or "").strip():
                return True
    return False


def lead_quality(*, obj: dict, company: dict | None, people: list[dict], confidence: int) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []

    has_object = bool(str(obj.get("name") or "").strip() and str(obj.get("address") or "").strip())
    photo_ok = has_probable_exterior_photo(obj)
    cadastre_ok = bool(obj.get("cadastral_number"))
    owner_ok = bool(company and company.get("inn"))
    person_contact_ok = has_person_contact(people)

    if not has_object:
        reasons.append("нет полноценного объекта с названием и адресом")
    if not photo_ok:
        reasons.append("нет подтвержденного фото фасада снаружи")
    else:
        warnings.append("фото нужно визуально проверить: фасад/экстерьер, не интерьер и не логотип")
    if not cadastre_ok:
        warnings.append("кадастровый объект не найден бесплатными источниками")
    if not owner_ok:
        reasons.append("владелец/юрлицо здания не подтверждено")
    if not person_contact_ok:
        warnings.append("нет публичного контакта конкретного ЛПР/владельца")
    if confidence < 70:
        warnings.append("низкая уверенность связи объект -> владелец")

    if has_object and photo_ok and owner_ok and person_contact_ok:
        status = "ready_owner_contact"
        label = "Владелец + контакт"
    elif has_object and photo_ok and owner_ok:
        status = "ready_owner_only"
        label = "Владелец найден"
    elif has_object and not photo_ok and owner_ok:
        status = "needs_photo"
        label = "Нужно фото фасада"
    elif has_object and photo_ok and not owner_ok:
        status = "needs_owner"
        label = "Нужен владелец"
    elif has_object:
        status = "needs_object_enrichment"
        label = "Добрать объект"
    else:
        status = "rejected"
        label = "Отклонить"

    return {
        "status": status,
        "label": label,
        "object_ok": has_object,
        "photo_ok": photo_ok,
        "cadastre_ok": cadastre_ok,
        "owner_ok": owner_ok,
        "person_contact_ok": person_contact_ok,
        "reasons": reasons,
        "warnings": warnings,
    }
