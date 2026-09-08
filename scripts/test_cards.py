"""Run full contact investigator on sample companies (Agent 2+3)."""
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
from app.llm import RouterAI


SAMPLES = [
    ("ozon", "7704217370"),
    ("pyaterochka", "6907009824"),
    ("factory", "5836684024"),
]


def _summary(party: dict) -> dict:
    p = party.get("presence") or {}
    return {
        "name": party.get("name"),
        "inn": party.get("inn"),
        "phone": (p.get("phone") or {}).get("value"),
        "email": (p.get("email") or {}).get("value"),
        "site": (p.get("site") or {}).get("value"),
        "vk": (p.get("vk_company") or {}).get("value"),
        "tg": (p.get("telegram") or {}).get("value"),
        "wa": (p.get("whatsapp") or {}).get("value"),
        "max": (p.get("max") or {}).get("value"),
        "vk_lpr": (p.get("vk_lpr") or {}).get("value"),
        "recommend": p.get("recommend"),
        "object_hint": (p.get("object_hint") or {}).get("value"),
        "photos": len(party.get("photos") or []),
        "checks_tail": (p.get("checks") or [])[-6:],
    }


async def main() -> None:
    settings = load_settings()
    llm = RouterAI(
        settings.router_api_key,
        base_url=settings.router_base_url,
        model=settings.router_model,
    )
    dadata = DaData(settings.dadata_api_key)
    out: dict = {"llm": llm.available, "cards": []}

    try:
        for label, inn in SAMPLES:
            print(f"\n=== {label} INN {inn} ===")
            raw = await dadata.find_by_inn(inn)
            if not raw:
                print("no dadata")
                continue
            party = enrich_from_dadata(raw)
            party = await enrich_contacts(party, llm=llm)
            card = _summary(party)
            out["cards"].append({"label": label, **card})
            print(json.dumps(card, ensure_ascii=False, indent=2))
    finally:
        await dadata.aclose()
        await llm.aclose()

    path = "/tmp/niteos_test_cards.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nWrote", path)


if __name__ == "__main__":
    asyncio.run(main())
