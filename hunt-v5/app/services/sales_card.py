from __future__ import annotations
from typing import Iterable

DIRECT_CONTACT_TYPES = {
    "phone",
    "email",
    "telegram",
    "vk",
    "ok",
    "instagram",
    "tenchat",
    "whatsapp",
    "max",
    "linkedin",
    "profile",
    "professional_profile",
    "messenger",
}

ROLE_PRIORITY = {
    "chief_engineer": 100,
    "technical_director": 97,
    "chief_power_engineer": 95,
    "facility_director": 93,
    "capital_construction": 92,
    "operations_director": 90,
    "general_director": 78,
    "chief_metallurgist": 72,
    "ultimate_identified_owner": 68,
}


def has_actionable_contact(person: dict) -> bool:
    for c in person.get("contacts") or []:
        if c.get("status") not in {"confirmed", "probable"}:
            continue
        ctype = c.get("type") or c.get("contact_type")
        if ctype not in DIRECT_CONTACT_TYPES:
            continue
        if not str(c.get("value") or "").strip():
            continue
        return True
    return False


def actionable_people(people: Iterable[dict]) -> list[dict]:
    """Sales UI rule: do not show people with no usable public contact."""
    out = [p for p in people if has_actionable_contact(p)]
    out.sort(key=lambda p: ROLE_PRIORITY.get(p.get("role", ""), 0), reverse=True)
    return out


def lighting_score(*, photo_url: str = "", panorama_url: str = "", road_visible: bool = False,
                   facade_area_signal: bool = False, entrance_signal: bool = False,
                   architectural_rhythm_signal: bool = False, signage_signal: bool = False) -> dict:
    score = 0
    reasons = []
    if photo_url:
        score += 20; reasons.append("есть фото фасада")
    if panorama_url:
        score += 20; reasons.append("есть уличная панорама")
    if road_visible:
        score += 25; reasons.append("фасад виден с дороги")
    if facade_area_signal:
        score += 15; reasons.append("есть выразительная плоскость фасада")
    if entrance_signal:
        score += 8; reasons.append("выраженная входная группа")
    if architectural_rhythm_signal:
        score += 7; reasons.append("ритм окон/простенков пригоден для акцентного света")
    if signage_signal:
        score += 5; reasons.append("есть вывеска/бренд-зона")
    return {
        "score": min(score, 100),
        "status": "high" if score >= 75 else "medium" if score >= 50 else "low",
        "reasons": reasons,
    }
