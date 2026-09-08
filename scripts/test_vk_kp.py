"""Smoke: VK group parse + KP draft for one INN."""
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
from app.kp import generate_kp
from app.llm import RouterAI

INN = os.environ.get("TEST_INN", "1654042667")  # GUM Kazan


async def main() -> None:
    settings = load_settings()
    llm = RouterAI(
        settings.router_api_key,
        base_url=settings.router_base_url,
        model=settings.router_model,
    )
    dadata = DaData(settings.dadata_api_key)
    try:
        raw = await dadata.find_by_inn(INN)
        if not raw:
            print("no dadata for", INN)
            return
        party = enrich_from_dadata(raw)
        party = await enrich_contacts(party, llm=llm)
        party["sphere"] = "shops"
        kp = await generate_kp(llm, party)
        p = party.get("presence") or {}
        vk = p.get("vk_group") or {}
        out = {
            "inn": INN,
            "name": party.get("name"),
            "vk_company": (p.get("vk_company") or {}).get("value"),
            "vk_group": {
                "url": vk.get("value"),
                "title": vk.get("title"),
                "contacts": vk.get("contacts") or [],
                "phones": vk.get("phones") or [],
            },
            "kp_title": kp.get("title"),
            "kp_message": kp.get("message_short"),
            "kp_products": kp.get("products") or [],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        with open("/tmp/niteos_vk_kp.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    finally:
        await dadata.aclose()
        await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
