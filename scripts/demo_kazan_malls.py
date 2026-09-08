"""Demo: 5 Kazan mall buildings → UK cards. Re-enrich even if INN already in DB."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from app.config import load_settings
from app.db import connect
from app import db
from app.dadata import DaData
from app.contacts import enrich_contacts
from app.enrich import FnsBfo, enrich_from_dadata, merge_fns_finance
from app.llm import RouterAI
from app.objects import (
    collect_object_photos,
    is_building_grade_title,
    is_tenant_inside_host,
    object_company_relation,
    recommend_object,
    search_objects,
    streetish_address,
)
from app.qualification import qualify_lead
from app.agents import company_card, _filter_object_photos, _score


async def main() -> None:
    settings = load_settings()
    database = await connect(settings)
    dadata = DaData(settings.dadata_api_key)
    fns = FnsBfo()
    llm = RouterAI(settings)
    cities = ["Казань"]
    query = "торговый центр"
    target = 5

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    cards: list[dict] = []
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=headers) as http:
        print("SEARCH_OBJECTS", flush=True)
        objects = await search_objects(http, query=query, cities=cities, limit=20)
        buildings = []
        for obj in objects:
            title = str(obj.get("title") or "")
            if is_tenant_inside_host(title):
                continue
            rec = recommend_object(
                title=title,
                address=str(obj.get("address") or ""),
                query=query,
                sphere="commercial",
            )
            if not rec.get("ok"):
                continue
            if not is_building_grade_title(title, query) and "тц" not in title.lower() and "трц" not in title.lower():
                continue
            buildings.append((obj, rec))
        print(f"BUILDINGS {len(buildings)}", flush=True)

        for obj, rec in buildings:
            if len(cards) >= target:
                break
            name_q = str(obj.get("title") or "").strip()
            city_q = str(obj.get("city") or "Казань")
            suggestions: list[dict] = []
            for dq in (
                f"{name_q} управляющая компания",
                f"УК {name_q}",
                f"{name_q} {city_q}",
                name_q,
            ):
                try:
                    suggestions.extend(await dadata.suggest(dq, count=6, locations=[{"city": "Казань"}]))
                except Exception as exc:
                    print("DADATA_ERR", dq, exc, flush=True)
            if not suggestions:
                cards.append(
                    {
                        "building": name_q,
                        "address": obj.get("address") or "",
                        "company": "—",
                        "inn": "—",
                        "verdict": "building_only_no_uk",
                        "photos": 0,
                        "vk": False,
                        "site": False,
                    }
                )
                print("CARD_BUILDING_ONLY", name_q, flush=True)
                continue

            def rank(item: dict) -> int:
                data = item.get("data") or {}
                name = str(item.get("value") or "").lower()
                score = 0
                if any(w in name for w in ("управл", "ук ", "ук«")):
                    score += 40
                if any(w in name for w in ("магазин", "ресторан", "гостиниц", "отел")):
                    score -= 40
                return score

            suggestions = sorted(suggestions, key=rank, reverse=True)
            item = suggestions[0]
            party = enrich_from_dadata(item)
            inn = party.get("inn") or ""
            if not inn:
                continue
            # attach building
            photos, photo_notes = await collect_object_photos(
                http, {**obj, "city": city_q}
            )
            party["object"] = {
                "title": obj.get("title") or "",
                "address": obj.get("address") or "",
                "source": obj.get("source") or "",
                "url_2gis": obj.get("url_2gis") or "",
                "url_osm": obj.get("url_osm") or "",
                "maps_yandex": obj.get("maps_yandex") or "",
                "maps_google": obj.get("maps_google") or "",
                "recommend": rec,
                "relation": object_company_relation(party, obj),
                "photo_notes": photo_notes,
            }
            party["photos"] = photos
            party["object_address"] = obj.get("address") or ""
            party["sphere"] = "commercial"
            party["idea"] = "Архитектурная подсветка фасада / входа ТЦ"
            party["found_via"] = query

            print(f"ENRICH {name_q} → {party.get('name')} {inn}", flush=True)
            try:
                raw = await dadata.find_by_inn(inn)
                if raw:
                    party = {**party, **enrich_from_dadata(raw)}
                    # keep object
                    party["object"] = {
                        "title": obj.get("title") or "",
                        "address": obj.get("address") or "",
                        "source": obj.get("source") or "",
                        "url_2gis": obj.get("url_2gis") or "",
                        "url_osm": obj.get("url_osm") or "",
                        "maps_yandex": obj.get("maps_yandex") or "",
                        "maps_google": obj.get("maps_google") or "",
                        "recommend": rec,
                        "relation": object_company_relation(party, obj),
                        "photo_notes": photo_notes,
                    }
                    party["photos"] = photos
            except Exception as exc:
                print("INN_ERR", inn, exc, flush=True)

            flat = dict(party)
            flat = await merge_fns_finance(flat, fns)
            flat = await enrich_contacts(flat, llm=llm)
            flat["object"] = party["object"]
            if party.get("photos") and not flat.get("photos"):
                flat["photos"] = party["photos"]
            _filter_object_photos(flat)
            qualification = qualify_lead(flat)
            flat["qualification"] = qualification
            score, stamp, stamp_hint = _score(
                "commercial",
                flat.get("status") or "",
                bool(flat.get("management")),
                online_hits=int(flat.get("online_hits") or 0),
                has_finance=flat.get("revenue") is not None or flat.get("profit") is not None,
                object_confirmed=bool(qualification.get("object_confirmed")),
                non_object_legal_entity=bool(qualification.get("non_object_legal_entity")),
            )
            flat["stamp"] = stamp
            flat["score"] = score
            flat["stamp_hint"] = stamp_hint
            await db.save_company(database, flat)  # may already exist
            await db.update_company(
                database,
                inn,
                {
                    "name": flat.get("name"),
                    "address": flat.get("address"),
                    "status": flat.get("status"),
                    "okved": flat.get("okved"),
                    "stamp": stamp,
                    "score": score,
                    "payload_json": json.dumps(company_card(flat), ensure_ascii=False),
                },
            )
            presence = flat.get("presence") or {}
            title = str((flat.get("object") or {}).get("title") or "")
            verdict = "ok"
            if is_tenant_inside_host(title):
                verdict = "reject_tenant"
            elif not is_building_grade_title(title, query) and "тц" not in title.lower():
                verdict = "weak_building"
            cards.append(
                {
                    "building": title,
                    "address": (flat.get("object") or {}).get("address") or "",
                    "company": flat.get("name") or "—",
                    "inn": inn,
                    "relation": ((flat.get("object") or {}).get("relation") or {}).get("status"),
                    "photos": len(flat.get("photos") or []),
                    "site": bool((presence.get("site") or {}).get("value")),
                    "vk": bool((presence.get("vk_company") or {}).get("value")),
                    "stamp": stamp,
                    "score": score,
                    "verdict": verdict,
                    "streetish": streetish_address(str((flat.get("object") or {}).get("address") or "")),
                }
            )
            print("CARD", json.dumps(cards[-1], ensure_ascii=False), flush=True)

    path = ROOT / "data" / "kazan_malls_demo.json"
    path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE", path, flush=True)
    await database.close()
    await dadata.aclose() if hasattr(dadata, "aclose") else None


if __name__ == "__main__":
    asyncio.run(main())
