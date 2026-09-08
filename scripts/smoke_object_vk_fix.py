"""Smoke: named objects, photos, VK for Kazan malls."""
from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from app.contacts import _bing_links, _is_vk_url
from app.objects import (
    collect_object_photos,
    is_generic_object_title,
    search_objects,
)
from app.vk_group import is_vk_group_url

OUT = os.path.join(ROOT, "scripts", "_smoke_object_vk_out.json")


async def main() -> None:
    report: dict = {}
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        objs = await search_objects(
            client, query="торговый центр", cities=["Казань"], limit=8
        )
        report["objects"] = [
            {
                "title": o.get("title"),
                "generic": is_generic_object_title(
                    str(o.get("title") or ""), "торговый центр"
                ),
                "address": (o.get("address") or "")[:100],
                "maps": (o.get("maps_yandex") or "")[:120],
                "source": o.get("source"),
            }
            for o in objs
        ]
        named = [
            o
            for o in objs
            if not is_generic_object_title(str(o.get("title") or ""), "торговый центр")
        ]
        report["named_count"] = len(named)
        if named:
            sample = named[0]
            photos, notes = await collect_object_photos(client, sample)
            report["photo_sample"] = {
                "title": sample.get("title"),
                "count": len(photos),
                "photos": photos[:4],
                "notes": notes,
            }

        vk_report = {}
        for q in (
            "Порт Казань ВК",
            "МЕГГА ПАРК ВК",
            "МЕГА Казань ВК",
            "ТЦ Порт ВК Казань",
        ):
            links = await _bing_links(client, q)
            vk = [u for u in links if _is_vk_url(u)]
            groups = [u for u in vk if is_vk_group_url(u)]
            vk_report[q] = (groups or vk)[:4]
        report["vk"] = vk_report

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("wrote", OUT)
    print("named", report.get("named_count"))
    print("photos", (report.get("photo_sample") or {}).get("count"))
    for q, links in (report.get("vk") or {}).items():
        print("vk", q, "->", links or "NONE")


if __name__ == "__main__":
    asyncio.run(main())
