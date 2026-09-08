"""Enrich fresh SMB cards (bypass hunt DB) for demo."""
from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.config import load_settings
from app.contacts import enrich_contacts
from app.dadata import DaData
from app.enrich import enrich_from_dadata
from app.geo import dadata_locations
from app.llm import RouterAI


QUERIES = [
    ("магазин", "shops"),
    ("прачечная", "laundry"),
    ("завод", "industry"),
    ("склад", "warehouse"),
]


def _row(party: dict, segment: str) -> dict:
    p = party.get("presence") or {}
    return {
        "segment": segment,
        "name": party.get("name"),
        "inn": party.get("inn"),
        "city_hint": (party.get("address") or "")[:60],
        "lpr": (p.get("lpr") or {}).get("value"),
        "lpr_post": (p.get("lpr") or {}).get("post"),
        "phone": (p.get("phone") or {}).get("value"),
        "email": (p.get("email") or {}).get("value"),
        "site": (p.get("site") or {}).get("value"),
        "vk_co": (p.get("vk_company") or {}).get("value"),
        "vk_lpr": (p.get("vk_lpr") or {}).get("value"),
        "tg": (p.get("telegram") or {}).get("value"),
        "wa": (p.get("whatsapp") or {}).get("value"),
        "recommend": (p.get("recommend") or {}).get("value"),
        "object": (p.get("object_hint") or {}).get("value"),
        "photos": len(party.get("photos") or []),
        "checks": (p.get("checks") or [])[-4:],
    }


async def pick_inns(dadata: DaData, query: str, locations, n: int = 3) -> list[str]:
    items = await dadata.suggest(query, count=25, locations=locations)
    inns: list[str] = []
    for item in items:
        p = enrich_from_dadata(item)
        inn = p.get("inn") or ""
        addr = (p.get("address") or "").lower()
        name = (p.get("name") or "").lower()
        if not inn or inn in inns:
            continue
        if "казан" not in addr and "татарстан" not in addr:
            continue
        if any(
            x in name
            for x in ("озон", "ozon", "x5", "магнит", "тандер", "пятёрочка", "агроторг", "лента")
        ):
            continue
        inns.append(inn)
        if len(inns) >= n:
            break
    return inns


async def main() -> None:
    settings = load_settings()
    llm = RouterAI(
        settings.router_api_key,
        base_url=settings.router_base_url,
        model=settings.router_model,
    )
    dadata = DaData(settings.dadata_api_key)
    loc = dadata_locations("Россия", "Татарстан", "Казань", "")
    cards: list[dict] = []

    try:
        for query, segment in QUERIES:
            inns = await pick_inns(dadata, query, loc, n=3)
            print(f"\n## {segment} / {query}: {inns}")
            for inn in inns:
                raw = await dadata.find_by_inn(inn)
                if not raw:
                    continue
                party = enrich_from_dadata(raw)
                party = await enrich_contacts(party, llm=llm)
                card = _row(party, segment)
                cards.append(card)
                print(json.dumps(card, ensure_ascii=False, indent=2))
    finally:
        await dadata.aclose()
        await llm.aclose()

    report = {"city": "Казань", "cards": cards}
    with open("/tmp/niteos_demo_enrich.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    n = len(cards)
    print(
        f"\nИТОГО {n} | LPR {sum(1 for c in cards if c.get('lpr'))} | "
        f"phone {sum(1 for c in cards if c.get('phone'))} | "
        f"email {sum(1 for c in cards if c.get('email'))} | "
        f"vk {sum(1 for c in cards if c.get('vk_co') or c.get('vk_lpr'))} | "
        f"tg/wa {sum(1 for c in cards if c.get('tg') or c.get('wa'))}"
    )


if __name__ == "__main__":
    asyncio.run(main())
