"""Compare LPR/contact hit rate: big corps vs SMB."""
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


async def find_smb(dadata: DaData, query: str, n: int = 2) -> list[str]:
    items = await dadata.suggest(query, count=15)
    inns: list[str] = []
    for item in items:
        p = enrich_from_dadata(item)
        inn = p.get("inn") or ""
        emp = p.get("employee_count")
        name = (p.get("name") or "").lower()
        if not inn or inn in inns:
            continue
        # skip obvious giants
        if any(x in name for x in ("x5", "озон", "ozon", "газпром", "сбер", "лукойл", "магнит", "ао \"тандер\"")):
            continue
        if emp and isinstance(emp, int) and emp > 500:
            continue
        inns.append(inn)
        if len(inns) >= n:
            break
    return inns


def _lpr_summary(party: dict) -> dict:
    p = party.get("presence") or {}
    hits = sum(
        1
        for k in ("vk_company", "vk_lpr", "telegram", "whatsapp", "max", "web_lpr", "phone", "email")
        if (p.get(k) or {}).get("status") == "найдено"
    )
    return {
        "name": party.get("name"),
        "inn": party.get("inn"),
        "employees": party.get("employee_count"),
        "lpr": party.get("management_label") or party.get("management"),
        "post": party.get("management_post"),
        "founders": (party.get("founders") or [])[:2],
        "phone": (p.get("phone") or {}).get("value"),
        "email": (p.get("email") or {}).get("value"),
        "site": (p.get("site") or {}).get("value"),
        "vk_co": (p.get("vk_company") or {}).get("value"),
        "vk_lpr": (p.get("vk_lpr") or {}).get("value"),
        "tg": (p.get("telegram") or {}).get("value"),
        "wa": (p.get("whatsapp") or {}).get("value"),
        "max": (p.get("max") or {}).get("value"),
        "web_lpr": (p.get("web_lpr") or {}).get("value"),
        "recommend": (p.get("recommend") or {}).get("value"),
        "contact_hits": hits,
        "photos": len(party.get("photos") or []),
    }


async def main() -> None:
    settings = load_settings()
    llm = RouterAI(
        settings.router_api_key,
        base_url=settings.router_base_url,
        model=settings.router_model,
    )
    dadata = DaData(settings.dadata_api_key)
    results: list[dict] = []

    try:
        for label, query in [
            ("smb_shop", "продуктовый магазин Казань"),
            ("smb_laundry", "прачечная Казань"),
            ("smb_factory", "завод Казань"),
        ]:
            inns = await find_smb(dadata, query, n=2)
            print(f"\n## {label} found INNs: {inns}")
            for inn in inns:
                raw = await dadata.find_by_inn(inn)
                if not raw:
                    continue
                party = enrich_from_dadata(raw)
                party = await enrich_contacts(party, llm=llm)
                card = {"segment": label, **_lpr_summary(party)}
                results.append(card)
                print(json.dumps(card, ensure_ascii=False, indent=2))
    finally:
        await dadata.aclose()
        await llm.aclose()

    with open("/tmp/niteos_smb_lpr.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nWrote /tmp/niteos_smb_lpr.json")


if __name__ == "__main__":
    asyncio.run(main())
