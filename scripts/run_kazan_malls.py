"""Run building-first hunt: Kazan, malls, 5 cards. Print compact verdict."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.db import connect
from app.agents import run_hunt
from app.objects import is_building_grade_title, is_tenant_inside_host


async def main() -> None:
    settings = load_settings()
    database = await connect(settings)

    async def progress(msg: str) -> None:
        print("PROGRESS:", msg, flush=True)

    result = await run_hunt(
        settings=settings,
        database=database,
        user_id=1,
        sphere_ids=["commercial"],
        phrase="",
        okved_raw="",
        target_count=5,
        region="Татарстан",
        city="Казань",
        progress=progress,
        search_queries=["торговый центр"],
        cities=["Казань"],
        regions=["Татарстан"],
    )
    companies = result.get("companies") or result.get("results") or []
    if not companies and result.get("hunt_id"):
        # fallback: pull from DB payload if agent returns summary only
        from app import db as dbmod

        rows = await dbmod.list_hunt_companies(database, int(result["hunt_id"]))
        companies = rows or []

    out = []
    for i, c in enumerate(companies[:5], 1):
        payload = c.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        obj = c.get("object") or payload.get("object") or {}
        title = str(obj.get("title") or "")
        addr = str(obj.get("address") or c.get("object_address") or "")
        photos = c.get("photos") or payload.get("photos") or []
        presence = c.get("presence") or payload.get("presence") or {}
        vk = (presence.get("vk_company") or {}).get("value") or ""
        site = (presence.get("site") or {}).get("value") or ""
        rel = obj.get("relation") or {}
        verdict = "ok"
        if is_tenant_inside_host(title):
            verdict = "reject_tenant"
        elif not title or not is_building_grade_title(title, "торговый центр"):
            verdict = "weak_building"
        elif not addr:
            verdict = "no_address"
        out.append(
            {
                "n": i,
                "building": title or "—",
                "address": addr or "—",
                "company": c.get("name") or "—",
                "inn": c.get("inn") or "—",
                "relation": rel.get("status") or "—",
                "photos": len(photos) if isinstance(photos, list) else 0,
                "site": bool(site),
                "vk": bool(vk),
                "stamp": c.get("stamp") or "",
                "verdict": verdict,
            }
        )

    print("HUNT_SUMMARY", json.dumps({
        "hunt_id": result.get("hunt_id"),
        "found": len(out),
        "errors": (result.get("errors") or [])[:5],
        "cards": out,
    }, ensure_ascii=False, indent=2))
    await database.close()


if __name__ == "__main__":
    asyncio.run(main())
