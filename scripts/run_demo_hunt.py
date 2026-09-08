"""Full hunt demo: SMB companies in Kazan across 3 spheres."""
from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.agents import run_hunt
from app.config import load_settings
from app import db


SCENARIOS = [
    ("прачечные", ["laundry"], ["прачечная"], 3),
    ("магазины", ["shops"], ["магазин"], 3),
    ("заводы", ["industry"], ["завод"], 3),
]


def _card_row(c: dict) -> dict:
    p = c.get("presence") or {}
    social = sum(
        1
        for k in ("vk_company", "vk_lpr", "telegram", "whatsapp", "max")
        if (p.get(k) or {}).get("status") == "найдено"
    )
    return {
        "name": c.get("name"),
        "inn": c.get("inn"),
        "lpr": (p.get("lpr") or {}).get("value") or c.get("management_label"),
        "lpr_post": (p.get("lpr") or {}).get("post") or c.get("management_post"),
        "phone": (p.get("phone") or {}).get("value"),
        "email": (p.get("email") or {}).get("value"),
        "site": (p.get("site") or {}).get("value"),
        "vk_co": (p.get("vk_company") or {}).get("value"),
        "vk_lpr": (p.get("vk_lpr") or {}).get("value"),
        "tg": (p.get("telegram") or {}).get("value"),
        "wa": (p.get("whatsapp") or {}).get("value"),
        "recommend": (p.get("recommend") or {}).get("value"),
        "object": (p.get("object_hint") or {}).get("value"),
        "photos": len(c.get("photos") or []),
        "social_hits": social,
        "stamp": c.get("stamp_label"),
        "found_via": c.get("found_via"),
    }


async def main() -> None:
    settings = load_settings()
    database = await db.connect(settings)
    report: dict = {"city": "Казань", "runs": [], "cards": []}

    async def progress(text: str) -> None:
        line = text.replace("\n", " | ")
        if "Агент" in line or "готов" in line.lower():
            print(line[:160])

    try:
        for label, spheres, queries, count in SCENARIOS:
            print(f"\n========== {label} ==========")
            result = await run_hunt(
                settings=settings,
                database=database,
                user_id=0,
                sphere_ids=spheres,
                phrase="",
                okved_raw="",
                search_queries=queries,
                target_count=count,
                region="",
                city="Казань",
                progress=progress,
            )
            cards = [_card_row(c) for c in result.get("companies") or []]
            report["runs"].append(
                {
                    "label": label,
                    "queries": result.get("queries"),
                    "found": len(cards),
                    "skipped": result.get("skipped"),
                }
            )
            report["cards"].extend(cards)
            for card in cards:
                print(json.dumps(card, ensure_ascii=False))
    finally:
        await database.close()

    path = "/tmp/niteos_demo_hunt.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    total = len(report["cards"])
    with_phone = sum(1 for c in report["cards"] if c.get("phone"))
    with_email = sum(1 for c in report["cards"] if c.get("email"))
    with_vk = sum(1 for c in report["cards"] if c.get("vk_co") or c.get("vk_lpr"))
    with_social = sum(1 for c in report["cards"] if c.get("social_hits"))
    print(
        f"\nИТОГО: {total} карточек | телефон {with_phone} | email {with_email} | "
        f"ВК {with_vk} | любая соцсеть {with_social}"
    )
    print("Wrote", path)


if __name__ == "__main__":
    asyncio.run(main())
