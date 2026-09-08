"""Test card quality for УК ТЦ Кулахметова (INN 1658221160)."""
from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from app.config import load_settings
from app.contacts import enrich_contacts
from app.dadata import DaData
from app.enrich import FnsBfo, enrich_from_dadata, format_money_rub, merge_fns_finance
from app.llm import RouterAI
from app.objects import streetish_address
from urllib.parse import quote_plus, unquote

OUT = os.path.join(ROOT, "scripts", "_kulak_out.json")
INN = "1658221160"


async def main() -> None:
    s = load_settings()
    dadata = DaData(s.dadata_api_key)
    fns = FnsBfo()
    llm = RouterAI(s.router_api_key, base_url=s.router_base_url, model=s.router_model)
    try:
        raw = await dadata.find_by_inn(INN)
        flat = enrich_from_dadata(raw or {})
        flat["requested_city"] = "Казань"
        flat["search_phrase"] = "Кулахметова"
        label = (flat.get("name") or "").replace('ООО "', "").replace('"', "")
        legal = flat.get("address") or ""
        pin = f"{label} {legal}".strip()
        flat["object"] = {
            "title": "ТЦ Кулахметова",
            "address": legal if streetish_address(legal) else "Казань, ул. Кулахметова, 28",
            "maps_yandex": f"https://yandex.ru/maps/?text={quote_plus(pin or 'ТЦ Кулахметова Казань ул Кулахметова 28')}",
            "source": "company-address",
            "city": "Казань",
        }
        flat["object_address"] = flat["object"]["address"]
        flat = await merge_fns_finance(flat, fns)
        flat = await enrich_contacts(flat, llm=llm)
        maps = ((flat.get("presence") or {}).get("maps_yandex") or {}).get("value") or ""
        maps_q = unquote(maps.split("text=")[-1]) if "text=" in maps else maps
        report = {
            "name": flat.get("name"),
            "inn": flat.get("inn"),
            "director": flat.get("management_label"),
            "founders": flat.get("founders"),
            "founders_detail": flat.get("founders_detail"),
            "employee_count": flat.get("employee_count"),
            "revenue": format_money_rub(flat.get("revenue")),
            "profit": format_money_rub(flat.get("profit")),
            "assets": format_money_rub(flat.get("assets")),
            "legal_address": flat.get("address"),
            "object_address": (flat.get("object") or {}).get("address"),
            "streetish_object": streetish_address(
                str((flat.get("object") or {}).get("address") or "")
            ),
            "maps_query": maps_q[:180],
            "phone": ((flat.get("presence") or {}).get("phone") or {}).get("value"),
            "phone_sources": (flat.get("presence") or {}).get("phone_sources"),
            "vk": ((flat.get("presence") or {}).get("vk_company") or {}).get("value"),
            "routes": [
                r.get("title") for r in (flat.get("contact_routes") or [])[:12]
            ],
            "photos_n": len(flat.get("photos") or []),
        }
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("wrote", OUT)
    finally:
        await dadata.aclose()
        await fns.aclose()
        await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
