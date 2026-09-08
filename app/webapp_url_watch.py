from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot

from app.bot import publish_webapp
from app.config import ROOT, Settings
from app.edge_url import fetch_public_webapp_url, update_env_webapp_url

log = logging.getLogger(__name__)

ENV_PATH = Path(ROOT / ".env")
# On server DATA_DIR is /opt/niteos/data but .env lives in /opt/niteos/.env
SERVER_ENV = Path("/opt/niteos/.env")


def _env_path(settings: Settings) -> Path:
    if SERVER_ENV.exists():
        return SERVER_ENV
    return ENV_PATH


async def watch_public_url(bot: Bot, settings: Settings) -> None:
    """
    Keep WebApp URL in sync with Cloudflare quick tunnel on bypass host.
    trycloudflare.com меняется при перезапуске cloudflared — бот подхватывает сам.
    """
    env_path = _env_path(settings)
    seen = (settings.webapp_url or "").rstrip("/")
    if seen:
        try:
            await publish_webapp(bot, seen)
        except Exception:
            log.exception("initial webapp publish failed")

    while True:
        try:
            url = await fetch_public_webapp_url()
            if url and url != seen:
                changed = update_env_webapp_url(env_path, url)
                await publish_webapp(bot, url)
                seen = url
                log.info(
                    "webapp url synced -> %s (env %s)",
                    url,
                    "updated" if changed else "same",
                )
            elif not seen and url:
                await publish_webapp(bot, url)
                seen = url
        except Exception:
            log.exception("webapp url sync tick failed")
        await asyncio.sleep(45)
