"""Mini end-to-end: objects + photos + VK + short hunt slice."""
from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import aiosqlite
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from app.agents import run_hunt
from app.config import load_settings
from app.contacts import _bing_links, _is_vk_url
from app import db
from app.objects import collect_object_photos, search_objects
from app.vk_group import is_vk_group_url

OUT = os.path.join(ROOT, "scripts", "_e2e_fix_out.json")


async def main() -> None:
    report: dict = {"steps": []}
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        objs = await search_objects(
            client, query="торговый центр", cities=["Казань"], limit=5
        )
        report["objects"] = [
            {
                "title": o.get("title"),
                "address": (o.get("address") or "")[:120],
                "maps": o.get("maps_yandex"),
                "source": o.get("source"),
            }
            for o in objs
        ]
        if objs:
            photos, notes = await collect_object_photos(client, objs[0])
            report["photos"] = {"title": objs[0].get("title"), "n": len(photos), "urls": photos[:4], "notes": notes}

        vk_q = []
        for o in objs[:3]:
            t = str(o.get("title") or "")
            vk_q.extend([f"{t} ВК", f"{t} ВК Казань", f"{t} вконтакте"])
        vk_q.extend(["Порт Казань ВК", "ТЦ Порт Казань ВК", "ТЦ Республика Казань ВК"])
        vk_found = {}
        for q in list(dict.fromkeys(vk_q))[:8]:
            await asyncio.sleep(0.4)
            links = await _bing_links(client, q)
            vk = [
                u.split("?")[0].replace("://m.vk.com", "://vk.com")
                for u in links
                if _is_vk_url(u)
            ]
            groups = [u for u in vk if is_vk_group_url(u)]
            vk_found[q] = (groups or vk)[:3]
        report["vk"] = vk_found

    # Short hunt against local DB
    settings = load_settings()
    database = await aiosqlite.connect(os.path.join(ROOT, "data", "niteos_test_hunt.db"))
    database.row_factory = aiosqlite.Row
    await database.executescript(db.SCHEMA)
    await db._migrate(database)
    await database.commit()
    logs: list[str] = []

    async def progress(msg: str) -> None:
        logs.append(msg)

    try:
        result = await run_hunt(
            settings=settings,
            database=database,
            user_id=1,
            sphere_ids=["shops"],
            phrase="",
            okved_raw="",
            target_count=2,
            region="",
            city="Казань",
            progress=progress,
            hunt_id=None,
            search_queries=["торговый центр"],
            cities=["Казань"],
            regions=[],
        )
        companies = (result or {}).get("companies") or []
        report["hunt"] = {
            "n": len(companies),
            "cards": [
                {
                    "name": c.get("name"),
                    "object": (c.get("object") or {}).get("title"),
                    "address": (c.get("object") or {}).get("address"),
                    "photos": len(c.get("photos") or []),
                    "photo_notes": (c.get("object") or {}).get("photo_notes"),
                    "vk": ((c.get("presence") or {}).get("vk_company") or {}).get("value"),
                    "city_hint": (c.get("address") or "")[:80],
                }
                for c in companies
            ],
            "errors": (result or {}).get("errors") or [],
            "log_tail": logs[-8:],
        }
    finally:
        await database.close()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("wrote", OUT)


if __name__ == "__main__":
    asyncio.run(main())
