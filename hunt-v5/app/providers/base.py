from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class ObjectCandidate:
    external_id: str
    name: str
    address: str
    lat: float | None = None
    lon: float | None = None
    category: str = ""
    photo_url: str = ""
    source_url: str = ""
    source_provider: str = ""

@dataclass
class CadastreRecord:
    cadastral_number: str
    address: str = ""
    area: float | None = None
    cadastral_value: float | None = None
    owner_type: str = ""
    owner_name: str = ""
    owner_inn: str = ""
    owner_ogrn: str = ""
    source: str = ""
    source_url: str = ""
    match_confidence: int = 0

@dataclass
class FounderRecord:
    kind: str
    name: str
    inn: str = ""
    share_percent: float | None = None
    source: str = ""

@dataclass
class CompanyRecord:
    inn: str
    name: str
    ogrn: str = ""
    legal_address: str = ""
    status: str = ""
    revenue: float | None = None
    profit: float | None = None
    employees: int | None = None
    director_name: str = ""
    founders: list[FounderRecord] = field(default_factory=list)
    source: str = ""
    source_url: str = ""

@dataclass
class ContactCandidate:
    contact_type: str
    value: str
    source_url: str
    source_type: str
    name_match: bool = False
    company_match: bool = False
    role_match: bool = False
    city_match: bool = False
    explicit_person_link: bool = False

class ObjectProvider(Protocol):
    async def search(self, city: str, query: str, count: int) -> list[ObjectCandidate]: ...

class CadastreProvider(Protocol):
    async def resolve(self, obj: ObjectCandidate) -> CadastreRecord | None: ...

class CompanyProvider(Protocol):
    async def by_inn(self, inn: str) -> CompanyRecord | None: ...
