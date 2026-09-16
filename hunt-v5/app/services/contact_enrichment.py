from __future__ import annotations
import re
from app.providers.base import ContactCandidate
from app.providers.public_search import NormalizedPublicSearchProvider
from app.services.contact_query_planner import LlmContactQueryPlanner
from app.services.person_osint import PersonSignal, resolve_person_contacts

PHONE_RE = re.compile(r"(?:\+7|8)[\s\-(]*(?:\d[\s\-()]*){10,11}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SOCIAL_URL_PATTERNS = (
    (re.compile(r"https?://(?:www\.)?vk\.com/[A-Za-z0-9_.\_-]{4,}", re.I), "vk", "public_social_profile"),
    (re.compile(r"https?://(?:www\.)?ok\.ru/profile/\d{5,}", re.I), "ok", "public_social_profile"),
    (re.compile(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.\_-]{3,}", re.I), "instagram", "public_social_profile"),
    (re.compile(r"https?://t\.me/[A-Za-z0-9_]{4,}", re.I), "telegram", "public_social_profile"),
    (re.compile(r"https?://(?:www\.)?tenchat\.ru/[A-Za-z0-9_.\_-]{3,}", re.I), "tenchat", "public_social_profile"),
    (re.compile(r"https?://wa\.me/\d{8,15}", re.I), "whatsapp", "public_messenger_link"),
    (re.compile(r"https?://(?:www\.)?max\.ru/[A-Za-z0-9_.\_-]{3,}", re.I), "max", "public_social_profile"),
)
FIO_RE = re.compile(
    r"\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ][а-яё]{2,})?\b"
)
ROLE_QUERIES = [
    ("chief_engineer", "главный инженер"),
    ("chief_power_engineer", "главный энергетик"),
    ("technical_director", "технический директор"),
    ("facility_director", "директор по эксплуатации"),
    ("operations_director", "директор по производству"),
    ("property_manager", "управляющий объектом"),
    ("maintenance_manager", "руководитель эксплуатации"),
]
ROLE_TEXT = dict(ROLE_QUERIES + [("general_director", "генеральный директор"), ("ultimate_identified_owner", "владелец")])

class PublicPersonContactEnricher:
    """Public-source contact discovery for a known business person.

    No guessed phones, no private datasets. Every emitted value carries a URL where the
    contact was actually visible. Deterministic scoring is applied after extraction.
    """
    def __init__(self, search=None):
        self.search = search or NormalizedPublicSearchProvider()
        self.query_planner = LlmContactQueryPlanner()

    async def search_person(
        self, full_name: str, company: str, city: str, role: str = ""
    ) -> list[ContactCandidate]:
        resolved = await self.resolve(
            full_name=full_name,
            company=company,
            role=role,
            city=city,
        )
        out: list[ContactCandidate] = []
        for item in resolved:
            if item.get("status") not in {"confirmed", "probable"}:
                continue
            out.append(
                ContactCandidate(
                    contact_type=str(item.get("contact_type") or ""),
                    value=str(item.get("value") or ""),
                    source_url=str(item.get("source_url") or ""),
                    source_type=str(item.get("source_type") or "public_web"),
                    name_match=True,
                    company_match=True,
                    role_match=bool(role),
                    city_match=True,
                    explicit_person_link=True,
                )
            )
        return out

    async def resolve(self, *, full_name: str, company: str, role: str, city: str) -> list[dict]:
        queries = await self.query_planner.queries_for_person(
            full_name=full_name,
            company=company,
            role=role,
            city=city,
        )
        signals = []
        role_text = ROLE_TEXT.get(role, role.replace("_", " ")).lower()
        company_tokens = [
            x for x in re.findall(r"[а-яёa-z0-9]{5,}", company.lower().replace("ё", "е"))
            if x not in {"общество", "ответственностью", "ограниченной"}
        ]
        for q in queries:
            for hit in await self.search.search(q, limit=6):
                blob = f"{hit.title}\n{hit.snippet}"
                low = blob.lower().replace("ё", "е").replace("«", "").replace("»", "")
                company_match = sum(t in low for t in company_tokens[:4]) >= min(2, len(company_tokens[:4]))
                name_tokens = [x for x in full_name.lower().split() if len(x) > 3]
                person_match = sum(t in low for t in name_tokens) >= min(2, len(name_tokens))
                if not person_match:
                    continue
                role_match = bool(role_text and role_text in low)
                city_match = city.lower().replace("ё", "е") in low
                for val in PHONE_RE.findall(blob):
                    signals.append(PersonSignal(full_name, company, role, city, "phone", val.strip(), hit.url, "public_web", True, role_match, company_match, city_match))
                for val in EMAIL_RE.findall(blob):
                    signals.append(PersonSignal(full_name, company, role, city, "email", val.strip(), hit.url, "public_web", True, role_match, company_match, city_match))
                for pattern, ctype, source_type in SOCIAL_URL_PATTERNS:
                    values = set(pattern.findall(blob))
                    if pattern.search(hit.url or ""):
                        values.add(hit.url)
                    for val in values:
                        signals.append(PersonSignal(full_name, company, role, city, ctype, val, hit.url, source_type, True, role_match, company_match, city_match))
        return resolve_person_contacts(signals)

    async def search_role_people(self, company: str, city: str, limit: int = 4) -> list[dict]:
        people: list[dict] = []
        seen: set[str] = set()
        company_core = (company or "").replace("«", "").replace("»", "").replace('"', "")
        company_core = re.sub(r"\b(ООО|АО|ПАО|ЗАО|ОАО)\b", "", company_core, flags=re.I).strip()
        for role, role_text in ROLE_QUERIES:
            queries = [
                f'"{company_core}" "{role_text}"',
                f'"{company_core}" "{role_text}" {city}',
                f'{company_core} {role_text} {city}',
                f'site:tatcenter.ru/person {company_core} {role_text}',
                f'site:kazan-tr.gazprom.ru/about/managers {company_core}',
                f'"{company_core}" "{role_text}" телефон',
                f'"{company_core}" "{role_text}" email',
            ]
            for q in queries:
                for hit in await self.search.search(q, limit=5):
                    blob = f"{hit.title}\n{hit.snippet}"
                    low = blob.lower()
                    if role_text not in low:
                        continue
                    for fio in FIO_RE.findall(blob):
                        key = fio.lower()
                        if key in seen:
                            continue
                        if any(x.lower() in key for x in ("общество", "директор", "инженер")):
                            continue
                        seen.add(key)
                        people.append({
                            "full_name": fio,
                            "role": role,
                            "source": hit.url,
                        })
                        if len(people) >= limit:
                            return people
        return people
