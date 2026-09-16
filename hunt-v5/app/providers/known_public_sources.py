from __future__ import annotations

from app.providers.base import CadastreRecord, ObjectCandidate


AUCTION_SOURCE = (
    "https://new.etpgpb.ru/procedures/etp/1153171-otkrytyy-auktsion-na-povyshenie-"
    "v-elektronnoy-forme-po-prodazhe-nedvizhimogo-imuschestva-svedeniya-o-prodavtse-"
    "sobstvennike-imuschestva-ooo-gazprom-transgaz-kazan/"
)
COSMOS_KAZAN_SOURCE = "https://hotgrade.ru/hotel/kazan/cosmos-kazan-hotel-otel-kosmos-kazan"
COSMOS_KAZAN_CONTACT_SOURCE = "https://www.radissonhotels.com/ru-ru/hotels/radisson-individuals-kazan"
COSMOS_KAZAN_FINANCE_SOURCE = "https://companies.rbc.ru/id/1087746876821-ooo-rgs-kazan/"

_ROWS = [
    {
        "external_id": "known-public-kazan-16:50:000000:13166",
        "name": "Здание склада с пристроем",
        "address": "Республика Татарстан, г. Казань, ул. Тэцевская, Северо-Западный промышленный район",
        "category": "industrial_warehouse",
        "cadastral_number": "16:50:000000:13166",
        "area": 2035.9,
        "owner_name": 'ООО "Газпром трансгаз Казань"',
        "owner_inn": "1600000036",
        "owner_ogrn": "1021603624921",
        "tokens": ("склад", "производ", "пром", "база", "комплекс"),
    },
    {
        "external_id": "known-public-kazan-16:50:000000:10446",
        "name": "Гараж производственной базы",
        "address": "Республика Татарстан, г. Казань, ул. Тэцевская, Северо-Западный промышленный район",
        "category": "industrial_garage",
        "cadastral_number": "16:50:000000:10446",
        "area": 603.3,
        "owner_name": 'ООО "Газпром трансгаз Казань"',
        "owner_inn": "1600000036",
        "owner_ogrn": "1021603624921",
        "tokens": ("производ", "пром", "гараж", "база", "комплекс"),
    },
    {
        "external_id": "known-public-kazan-cosmos-hotel",
        "name": "Cosmos Kazan Hotel",
        "address": "Республика Татарстан, г. Казань, ул. Лесгафта, д. 7",
        "category": "hotel",
        "cadastral_number": "",
        "area": None,
        "owner_name": 'ООО "РГС Казань"',
        "owner_inn": "7725642985",
        "owner_ogrn": "1087746876821",
        "source_url": COSMOS_KAZAN_SOURCE,
        "owner_source_url": COSMOS_KAZAN_SOURCE,
        "tokens": ("отель", "гостиниц", "hotel", "cosmos", "космос"),
        "contacts": [
            {
                "contact_type": "phone",
                "value": "+7 (843) 235-23-50",
                "source_url": COSMOS_KAZAN_CONTACT_SOURCE,
                "label": "официальный телефон отеля",
            },
            {
                "contact_type": "email",
                "value": "cosmoskazan@radissonindividuals.com",
                "source_url": COSMOS_KAZAN_CONTACT_SOURCE,
                "label": "официальная почта отеля",
            },
        ],
    },
]


def known_public_object_candidates(city: str, query: str, count: int) -> list[ObjectCandidate]:
    city_low = (city or "").lower().replace("ё", "е")
    query_low = (query or "").lower().replace("ё", "е")
    if "казан" not in city_low:
        return []
    out: list[ObjectCandidate] = []
    for row in _ROWS:
        if not any(token in query_low for token in row["tokens"]):
            continue
        out.append(
            ObjectCandidate(
                external_id=row["external_id"],
                name=row["name"],
                address=row["address"],
                category=row["category"],
                source_url=row.get("source_url") or AUCTION_SOURCE,
                source_provider="known-public-source",
            )
        )
        if len(out) >= count:
            break
    return out


def known_public_cadastre(obj: ObjectCandidate) -> CadastreRecord | None:
    for row in _ROWS:
        if obj.external_id != row["external_id"]:
            continue
        if not row.get("cadastral_number"):
            return None
        return CadastreRecord(
            cadastral_number=row["cadastral_number"],
            address=row["address"],
            area=row["area"],
            cadastral_value=None,
            owner_type="legal_entity",
            owner_name=row["owner_name"],
            owner_inn=row["owner_inn"],
            owner_ogrn=row["owner_ogrn"],
            source="public-known-source",
            source_url=row.get("owner_source_url") or row.get("source_url") or AUCTION_SOURCE,
            match_confidence=96,
        )
    return None


def known_public_owner(title: str, address: str, city: str) -> dict | None:
    blob = f"{title} {address} {city}".lower().replace("ё", "е")
    generic_address_tokens = {"республика", "татарстан", "казань", "город", "район"}
    generic_name_tokens = {"hotel", "отель", "гостиница", "kazan", "казань"}
    for row in _ROWS:
        if "казан" not in blob:
            continue
        name_tokens = [
            x
            for x in (row["name"].lower().replace("ё", "е")).split()
            if len(x) >= 4 and x not in generic_name_tokens
        ]
        address_tokens = [
            x.strip(".,")
            for x in (row["address"].lower().replace("ё", "е")).split()
            if len(x.strip(".,д")) >= 4 and x.strip(".,") not in generic_address_tokens
        ]
        name_hit = bool(name_tokens) and any(x in blob for x in name_tokens)
        address_hit = sum(1 for x in address_tokens if x in blob) >= 2
        if not (name_hit or address_hit or row.get("external_id", "") in blob):
            continue
        if not row.get("owner_inn"):
            continue
        return {
            "inn": row["owner_inn"],
            "source": row.get("owner_source_url") or row.get("source_url") or AUCTION_SOURCE,
            "confidence": 82 if row.get("cadastral_number") else 70,
        }
    return None


def known_public_object_contacts(title: str, address: str, owner_inn: str = "") -> list[dict]:
    blob = f"{title} {address} {owner_inn}".lower().replace("ё", "е")
    generic_name_tokens = {"hotel", "отель", "гостиница", "kazan", "казань"}
    for row in _ROWS:
        if owner_inn and row.get("owner_inn") == owner_inn:
            return list(row.get("contacts") or [])
        name_tokens = [
            x
            for x in (row["name"].lower().replace("ё", "е")).split()
            if len(x) >= 4 and x not in generic_name_tokens
        ]
        if any(x in blob for x in name_tokens):
            return list(row.get("contacts") or [])
    return []
