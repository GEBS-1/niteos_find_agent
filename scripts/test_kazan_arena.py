"""Smoke: Kazan Arena photos + owner contacts + KP API."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from app.config import load_settings
from app.contacts import enrich_contacts
from app.dadata import DaData
from app.enrich import enrich_from_dadata
from app.llm import RouterAI
from app.objects import collect_object_photos, is_building_grade_title, is_sports_building_title
from app.owners import resolve_building_owners, candidate_party


async def main() -> None:
    settings = load_settings()
    llm = RouterAI(
        settings.router_api_key,
        base_url=settings.router_base_url,
        model=settings.router_model,
        timeout=90,
    )
    dadata = DaData(settings.dadata_api_key)
    obj = {
        "title": 'Стадион "Казань Арена"',
        "address": "Казань, проспект Хусаина Ямашева, 115А",
        "city": "Казань",
        "maps_yandex": "",
        "url_2gis": "",
        "url_osm": "",
    }
    print("building_grade", is_building_grade_title(obj["title"], "арена"))
    print("sports_grade", is_sports_building_title(obj["title"]))

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    async with httpx.AsyncClient(
        timeout=40.0, follow_redirects=True, headers=headers
    ) as client:
        photos, notes = await collect_object_photos(client, obj)
        print("PHOTOS", len(photos), notes)
        for u in photos[:4]:
            print(" ", u[:120])

        cands = await resolve_building_owners(
            http=client,
            dadata=dadata,
            obj=obj,
            city="Казань",
            llm=llm,
        )
        print("OWNERS", len(cands))
        party = None
        for cand in cands[:8]:
            if not cand.get("suggest"):
                continue
            p = enrich_from_dadata(cand["suggest"])
            if not p:
                continue
            print(
                " cand",
                cand.get("source"),
                p.get("inn"),
                (p.get("name") or "")[:70],
                "|",
                (p.get("management") or "")[:40],
            )
            if not party:
                party = p
        if not party:
            print("NO_PARTY")
            await llm.aclose()
            return

        party["object"] = {
            "title": obj["title"],
            "address": obj["address"],
            "city": "Казань",
        }
        party["requested_city"] = "Казань"
        party["photos"] = photos
        enriched = await enrich_contacts(party, client=client, llm=llm)
        pr = enriched.get("presence") or {}
        summary = {
            "inn": enriched.get("inn"),
            "name": enriched.get("name"),
            "management": enriched.get("management_label") or enriched.get("management"),
            "founders": (enriched.get("founders") or [])[:4],
            "photos_n": len(enriched.get("photos") or photos or []),
            "phone": (pr.get("phone") or {}).get("value"),
            "site": (pr.get("site") or {}).get("value"),
            "vk": (pr.get("vk_company") or {}).get("value"),
            "vk_lpr": (pr.get("vk_lpr") or {}).get("value"),
            "telegram": (pr.get("telegram") or {}).get("value"),
            "whatsapp": (pr.get("whatsapp") or {}).get("value"),
            "checks": (pr.get("checks") or [])[:12],
        }
        print("SUMMARY", json.dumps(summary, ensure_ascii=False, indent=2))
        out = ROOT / "data" / "kazan_arena_eval.json"
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", out)
    await llm.aclose()
    await dadata.aclose()


if __name__ == "__main__":
    asyncio.run(main())
