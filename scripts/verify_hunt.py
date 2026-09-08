"""Smoke-test hunt relevance on the server."""
from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.config import load_settings

from app.agents import _queries, _okved_prefixes
from app.dadata import DaData
from app.enrich import enrich_from_dadata
from app.match import matches_search_intent


async def probe(label: str, *, sphere_ids, phrase, search_queries, okved, city="Казань") -> None:
    prefixes = _okved_prefixes(sphere_ids, okved)
    jobs = _queries(sphere_ids, phrase, okved, search_queries=search_queries)
    api_okved = [p for p in prefixes if "." in p]
    print(f"\n=== {label} ===")
    print("jobs:", jobs)
    print("okved filter:", api_okved)

    key = load_settings().dadata_api_key
    if not key:
        print("skip dadata: no key")
        return
    d = DaData(key)
    taken = []
    try:
        for q in jobs[:4]:
            items = await d.suggest(q, count=8, okved=api_okved or None)
            for item in items:
                p = enrich_from_dadata(item)
                if not matches_search_intent(
                    p.get("name") or "",
                    phrase or (search_queries[0] if search_queries else ""),
                    okved=p.get("okved") or "",
                    okved_prefixes=prefixes,
                ):
                    continue
                taken.append(
                    {
                        "query": q,
                        "name": p.get("name"),
                        "inn": p.get("inn"),
                        "okved": p.get("okved"),
                    }
                )
                break
    finally:
        await d.aclose()
    print("sample:", json.dumps(taken, ensure_ascii=False, indent=2))


async def main() -> None:
    await probe(
        "Пятёрочка (ритейл)",
        sphere_ids=["shops"],
        phrase="",
        search_queries=["пятёрочка"],
        okved=[],
    )
    await probe(
        "Промка / завод",
        sphere_ids=["industry"],
        phrase="",
        search_queries=["завод"],
        okved=[],
    )
    await probe(
        "Только ОКВЭД склад",
        sphere_ids=[],
        phrase="",
        search_queries=[],
        okved=["52.10"],
    )


if __name__ == "__main__":
    asyncio.run(main())
