"""Demo providers — ONLY for pytest with DEMO_MODE=1.

Production hunt must never invent names like «Иванов Сергей Петрович».
"""
from __future__ import annotations

import hashlib

from app.config import settings
from app.providers.base import (
    ObjectCandidate,
    CadastreRecord,
    CompanyRecord,
    FounderRecord,
    ContactCandidate,
)


def _require_demo() -> None:
    if not settings.demo_mode:
        raise RuntimeError(
            "Demo providers blocked: DEMO_MODE=0. Real hunt uses Nominatim/2GIS + DaData + cadastre only."
        )


class DemoObjectProvider:
    async def search(self, city: str, query: str, count: int):
        _require_demo()
        names = [
            "Промышленный комплекс Альфа",
            "Складской терминал Восток",
            "Производственная площадка Норд",
            "Логистический центр Волга",
            "Завод Металл-Профиль",
        ]
        out = []
        for i, name in enumerate(names[:count]):
            seed = int(hashlib.sha1(f"{city}:{query}:{i}".encode()).hexdigest()[:6], 16)
            out.append(
                ObjectCandidate(
                    external_id=f"demo-{seed}",
                    name=name,
                    address=f"{city}, Промышленная улица, {10 + i}",
                    lat=55.78 + i * 0.003,
                    lon=49.12 + i * 0.004,
                    category=query,
                    photo_url="/static/demo-factory.svg",
                    source_url="https://example.local/map",
                    source_provider="demo",
                )
            )
        return out


class DemoCadastreProvider:
    async def resolve(self, obj):
        _require_demo()
        last = abs(hash(obj.external_id)) % 9999
        inn = f"1650{last:06d}"
        return CadastreRecord(
            cadastral_number=f"16:50:0101:{1000 + last}",
            address=obj.address,
            area=8200 + last % 3000,
            cadastral_value=180_000_000 + (last % 100) * 1_000_000,
            owner_type="legal_entity",
            owner_name=f'ООО "Альфа Инвест {last % 7 + 1}"',
            owner_inn=inn,
            owner_ogrn=f"1161690{last:06d}",
            source="demo-cadastre",
            source_url="https://example.local/cadastre",
            match_confidence=98,
        )


class DemoCompanyProvider:
    async def by_inn(self, inn):
        _require_demo()
        if inn == "7700000000":
            return CompanyRecord(
                inn=inn,
                name='ООО "Альфа Холдинг"',
                ogrn="1027700000000",
                legal_address="Москва",
                status="ACTIVE",
                revenue=1_250_000_000,
                profit=140_000_000,
                employees=210,
                director_name="Петров Андрей Иванович",
                founders=[
                    FounderRecord(
                        kind="person",
                        name="Петров Андрей Иванович",
                        share_percent=80,
                        source="demo-registry",
                    ),
                    FounderRecord(
                        kind="person",
                        name="Сидоров Максим Олегович",
                        share_percent=20,
                        source="demo-registry",
                    ),
                ],
                source="demo-registry",
                source_url="https://example.local/registry",
            )
        suffix = int(inn[-2:]) if inn[-2:].isdigit() else 1
        return CompanyRecord(
            inn=inn,
            name=f'ООО "Альфа Инвест {suffix % 7 + 1}"',
            ogrn=f"1161690{suffix:06d}",
            legal_address="Казань",
            status="ACTIVE",
            revenue=640_000_000 + suffix * 1_000_000,
            profit=74_000_000 + suffix * 100_000,
            employees=83,
            director_name="Иванов Сергей Петрович",
            founders=[
                FounderRecord(
                    kind="person",
                    name="Иванов Сергей Петрович",
                    share_percent=70,
                    source="demo-registry",
                ),
                FounderRecord(
                    kind="company",
                    name='ООО "Альфа Холдинг"',
                    inn="7700000000",
                    share_percent=30,
                    source="demo-registry",
                ),
            ],
            source="demo-registry",
            source_url="https://example.local/registry",
        )


class DemoContactProvider:
    async def search_person(self, full_name, company_name, city, role):
        _require_demo()
        first = full_name.split()[0].lower()
        return [
            ContactCandidate(
                "phone",
                "+7 917 555-12-34",
                "https://example.local/professional-profile",
                "public_professional_profile",
                True,
                True,
                True,
                True,
                True,
            ),
            ContactCandidate(
                "telegram",
                f"@{first}_work",
                "https://example.local/company-team",
                "company_team_page",
                True,
                True,
                True,
                True,
                True,
            ),
            ContactCandidate(
                "email",
                f"{first}@alpha-demo.example",
                "https://example.local/company-team",
                "company_team_page",
                True,
                True,
                True,
                True,
                True,
            ),
        ]
