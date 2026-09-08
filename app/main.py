from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot import publish_webapp, run_polling
from app.config import load_settings
from app.db import connect
from app.edge_url import fetch_public_webapp_url, update_env_webapp_url
from app.webapp import HuntRuntime, start_http, worker
from app.webapp_url_watch import watch_public_url

log = logging.getLogger(__name__)
SERVER_ENV = Path("/opt/niteos/.env")


async def _bootstrap_webapp_url() -> str:
    """On start: live URL from bypass Cloudflare log (not stale .env)."""
    url = await fetch_public_webapp_url()
    if not url:
        return ""
    env_path = SERVER_ENV if SERVER_ENV.exists() else Path(__file__).resolve().parent.parent / ".env"
    update_env_webapp_url(env_path, url)
    return url


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    live_url = await _bootstrap_webapp_url()
    webapp_url = live_url or (settings.webapp_url or "").rstrip("/")
    if live_url and live_url != (settings.webapp_url or "").rstrip("/"):
        log.info("webapp url on boot: %s (was %s)", live_url, settings.webapp_url or "—")

    database = await connect(settings)
    runtime = HuntRuntime(settings, database)
    runner = await start_http(runtime)

    session = None
    if settings.telegram_proxy:
        session = AiohttpSession(proxy=settings.telegram_proxy)
        log.info("telegram proxy %s", settings.telegram_proxy)
    bot = Bot(settings.bot_token, session=session)
    bot.webapp_url = webapp_url
    bot.webapp_token = settings.webapp_token

    if webapp_url:
        try:
            await publish_webapp(bot, webapp_url)
        except Exception:
            log.exception("boot webapp publish failed")

    try:
        await asyncio.gather(
            run_polling(settings, database, bot=bot),
            worker(runtime),
            watch_public_url(bot, settings),
        )
    finally:
        await runner.cleanup()
        await database.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
