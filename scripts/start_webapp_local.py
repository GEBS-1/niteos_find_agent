from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.db import connect
from app.webapp import HuntRuntime, start_http, worker


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    database = await connect(settings)
    runtime = HuntRuntime(settings, database)
    runner = await start_http(runtime)
    task = asyncio.create_task(worker(runtime))
    try:
        await asyncio.Event().wait()
    finally:
        task.cancel()
        await runner.cleanup()
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
