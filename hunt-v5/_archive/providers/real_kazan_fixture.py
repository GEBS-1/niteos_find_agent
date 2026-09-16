from __future__ import annotations

from app.providers.base import (
    ObjectCandidate, CadastreRecord, CompanyRecord, FounderRecord, ContactCandidate
)

AUCTION_SOURCE = "https://new.etpgpb.ru/procedures/etp/1153171-otkrytyy-auktsion-na-povyshenie-v-elektronnoy-forme-po-prodazhe-nedvizhimogo-imuschestva-svedeniya-o-prodavtse-sobstvennike-imuschestva-ooo-gazprom-transgaz-kazan/"
COMPANY_SOURCE = "https://companies.rbc.ru/id/1021603624921-ooo-gazprom-transgaz-kazan/"
MANAGEMENT_SOURCE = "https://kazan-tr.gazprom.ru/about/managers/"
ABOUT_SOURCE = "https://kazan-tr.gazprom.ru/about/"

class RealKazanObjectProvider:
    """
    Two real Kazan industrial objects discovered from a public asset-sale source.
    This provider is a reproducible research fixture, not a fake/demo generator.
    """
    async def search(self, city: str, query: str, count: int):
        if "казан" not in city.lower():
            return []
        rows = [
            ObjectCandidate(
                external_id="real-kazan-16:50:000000:10446",
                name="Гараж производственной базы",
                address="Республика Татарстан, г. Казань, ул. Тэцевская, Северо-Западный промышленный район",
                lat=None,
                lon=None,
                category="industrial_garage",
                photo_url="",
                source_url=AUCTION_SOURCE,
                source_provider="ETP GPB / public auction",
            ),
            ObjectCandidate(
                external_id="real-kazan-16:50:000000:13166",
                name="Здание склада с пристроем",
                address="Республика Татарстан, г. Казань, ул. Тэцевская, Северо-Западный промышленный район",
                lat=None,
                lon=None,
                category="industrial_warehouse",
                photo_url="",
                source_url=AUCTION_SOURCE,
                source_provider="ETP GPB / public auction",
            ),
        ]
        return rows[:count]


class RealKazanCadastreProvider:
    async def resolve(self, obj: ObjectCandidate):
        if obj.external_id.endswith("10446"):
            return CadastreRecord(
                cadastral_number="16:50:000000:10446",
                address=obj.address,
                area=603.3,
                cadastral_value=None,
                owner_type="legal_entity",
                owner_name='ООО "Газпром трансгаз Казань"',
                owner_inn="1600000036",
                owner_ogrn="1021603624921",
                source="ЭТП ГПБ — продавец указан как собственник имущества",
                source_url=AUCTION_SOURCE,
                match_confidence=100,
            )
        if obj.external_id.endswith("13166"):
            return CadastreRecord(
                cadastral_number="16:50:000000:13166",
                address=obj.address,
                area=2035.9,
                cadastral_value=None,
                owner_type="legal_entity",
                owner_name='ООО "Газпром трансгаз Казань"',
                owner_inn="1600000036",
                owner_ogrn="1021603624921",
                source="ЭТП ГПБ — продавец указан как собственник имущества",
                source_url=AUCTION_SOURCE,
                match_confidence=100,
            )
        return None


class RealKazanCompanyProvider:
    async def by_inn(self, inn: str):
        if inn == "1600000036":
            return CompanyRecord(
                inn="1600000036",
                name='ООО "Газпром трансгаз Казань"',
                ogrn="1021603624921",
                legal_address="420073, Республика Татарстан, г. Казань, ул. Аделя Кутуя, д. 41",
                status="ACTIVE",
                revenue=46_539_346_000,
                profit=101_701_000,
                employees=None,
                director_name="Усманов Рустем Ринатович",
                founders=[
                    FounderRecord(
                        kind="company",
                        name='ПАО "Газпром"',
                        inn="7736050003",
                        share_percent=100.0,
                        source=COMPANY_SOURCE,
                    )
                ],
                source="РБК Компании / публичные реестровые сведения",
                source_url=COMPANY_SOURCE,
            )
        # We deliberately stop rather than invent Gazprom's ultimate human owners.
        if inn == "7736050003":
            return CompanyRecord(
                inn="7736050003",
                name='ПАО "Газпром"',
                ogrn="1027700070518",
                legal_address="",
                status="ACTIVE",
                founders=[],
                source="public registry chain; shareholder-level human UBO is not asserted",
                source_url=COMPANY_SOURCE,
            )
        return None


class RealKazanContactProvider:
    async def search_person(self, full_name: str, company_name: str, city: str, role: str):
        # No fabricated personal phone/email.
        # We only return a company-level channel when source is official and mark explicit_person_link=False.
        if full_name == "Усманов Рустем Ринатович":
            return [
                ContactCandidate(
                    contact_type="company_channel",
                    value="ООО «Газпром трансгаз Казань» — официальный сайт",
                    source_url=MANAGEMENT_SOURCE,
                    source_type="official_company_management_page",
                    name_match=True,
                    company_match=True,
                    role_match=True,
                    city_match=True,
                    explicit_person_link=False,
                )
            ]
        return []
