from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass
class PersonSignal:
    full_name: str
    company: str
    role: str
    city: str
    contact_type: str
    value: str
    source_url: str
    source_type: str
    published_for_person: bool = False
    current_role_match: bool = False
    company_match: bool = False
    city_match: bool = False
    historical: bool = False


@dataclass
class ResolvedPersonContact:
    contact_type: str
    value: str
    source_url: str
    source_type: str
    confidence: int
    status: str
    historical: bool
    reason: str


def score_signal(s: PersonSignal) -> tuple[int, str, str]:
    """Deterministic contact attribution; LLM is never allowed here."""
    score = 0
    reasons: list[str] = []
    if s.published_for_person:
        score += 45
        reasons.append("контакт опубликован на странице конкретного человека")
    if s.company_match:
        score += 25
        reasons.append("совпадает компания")
    if s.current_role_match:
        score += 20
        reasons.append("совпадает должность")
    if s.city_match:
        score += 10
        reasons.append("совпадает город")
    if s.source_type == "public_social_profile" and s.published_for_person and s.company_match:
        score += 15
        reasons.append("публичный соцпрофиль совпадает по ФИО и компании")
    if s.historical:
        score = min(score, 69)
        reasons.append("исторический источник — не считать текущим контактом")

    status = "confirmed" if score >= 90 else "probable" if score >= 70 else "historical" if s.historical else "unverified"
    return score, status, "; ".join(reasons)


def resolve_person_contacts(signals: Iterable[PersonSignal]) -> list[dict]:
    out: list[ResolvedPersonContact] = []
    seen: set[tuple[str, str]] = set()
    for s in signals:
        key = (s.contact_type.strip().lower(), s.value.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        score, status, reason = score_signal(s)
        out.append(ResolvedPersonContact(
            contact_type=s.contact_type,
            value=s.value,
            source_url=s.source_url,
            source_type=s.source_type,
            confidence=score,
            status=status,
            historical=s.historical,
            reason=reason,
        ))
    out.sort(key=lambda x: x.confidence, reverse=True)
    return [asdict(x) for x in out]
