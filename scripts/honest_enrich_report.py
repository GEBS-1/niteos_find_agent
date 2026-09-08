"""Honest enrich report: what actually fills for SMB Kazan."""
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

INNS = ["1654042667", "1650032058", "1683000015"]  # GUM + pick from hunt


async def pick_smb_inns(dadata: DaData, n: int = 4) -> list[str]:
    loc = dadata_locations("Россия", "Татарстан", "Казань", "")
    inns: list[str] = []
    for q in ("прачечная", "склад", "магазин одежды"):
        items = await dadata.suggest(q, count=20, locations=loc)
        for item in items:
            p = enrich_from_dadata(item)
            inn = p.get("inn") or ""
            addr = (p.get("address") or "").lower()
            name = (p.get("name") or "").lower()
            if not inn or inn in inns:
                continue
            if "казан" not in addr and "татарстан" not in addr:
                continue
            if any(x in name for x in ("озон", "x5", "магнит", "агроторг", "лента")):
                continue
            inns.append(inn)
            if len(inns) >= n:
                return inns
    return inns


def row(party: dict) -> dict:
    p = party.get("presence") or {}
    def v(k: str) -> str:
        return (p.get(k) or {}).get("value") or ""
    photos = party.get("photos") or (p.get("photos") or {}).get("value") or []
    return {
        "name": (party.get("name") or "")[:50],
        "inn": party.get("inn"),
        "phone": v("phone"),
        "email": v("email"),
        "site": v("site"),
        "vk": v("vk_company"),
        "tg": v("telegram"),
        "wa": v("whatsapp"),
        "max": v("max"),
        "recommend": (p.get("recommend") or {}).get("value"),
        "photos_n": len(photos),
        "photo_sample": photos[:2],
        "kp": bool((party.get("kp") or {}).get("title")),
        "checks_tail": (p.get("checks") or [])[-3:],
    }


async def main() -> None:
    settings = load_settings()
    llm = RouterAI(
        settings.router_api_key,
        base_url=settings.router_base_url,
        model=settings.router_model,
    )
    dadata = DaData(settings.dadata_api_key)
    cards: list[dict] = []
    try:
        inns = await pick_smb_inns(dadata, 4)
        print("INNs:", inns, flush=True)
        for inn in inns:
            raw = await dadata.find_by_inn(inn)
            if not raw:
                continue
            party = enrich_from_dadata(raw)
            party = await enrich_contacts(party, llm=llm)
            cards.append(row(party))
            print(json.dumps(cards[-1], ensure_ascii=False), flush=True)
    finally:
        await dadata.aclose()
        await llm.aclose()

    n = len(cards)
    summary = {
        "n": n,
        "phone": sum(1 for c in cards if c["phone"]),
        "email": sum(1 for c in cards if c["email"]),
        "site": sum(1 for c in cards if c["site"]),
        "vk": sum(1 for c in cards if c["vk"]),
        "tg_wa": sum(1 for c in cards if c["tg"] or c["wa"]),
        "photos": sum(1 for c in cards if c["photos_n"] > 0),
        "recommend": sum(1 for c in cards if c["recommend"]),
    }
    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    with open("/tmp/niteos_honest_enrich.json", "w", encoding="utf-8") as f:
        json.dump({"cards": cards, "summary": summary}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
