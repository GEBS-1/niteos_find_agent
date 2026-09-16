from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.public_registry_objects import PublicRegistryObjectProvider


async def main() -> None:
    provider = PublicRegistryObjectProvider()
    for query in ["гостиница", "бизнес центр", "складской комплекс", "производственный комплекс"]:
        started = time.time()
        rows = await provider.search("Казань", query, 2)
        print(
            json.dumps(
                {
                    "query": query,
                    "seconds": round(time.time() - started, 1),
                    "count": len(rows),
                    "rows": [
                        {
                            "name": row.name,
                            "address": row.address,
                            "source_url": row.source_url,
                            "source_provider": row.source_provider,
                        }
                        for row in rows
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
