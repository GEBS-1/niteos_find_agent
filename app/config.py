from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _need(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"В .env нет {name}")
    return value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    dadata_api_key: str
    region: str
    city: str
    db_path: Path
    webhook_url: str
    webhook_secret: str
    telegram_proxy: str
    webapp_url: str
    webapp_port: int
    webapp_token: str
    webapp_password: str
    session_secret: str
    router_api_key: str
    router_base_url: str
    router_model: str
    allowed_user_ids: frozenset[int]


def load_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    router_key = (
        os.getenv("ROUTERAI_API_KEY", "").strip()
        or os.getenv("ROUTER_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )
    from app.access import parse_allowed_user_ids

    webapp_token = os.getenv("WEBAPP_TOKEN", "").strip()
    router_base = (
        os.getenv("ROUTERAI_BASE_URL", "").strip()
        or os.getenv("OPENAI_BASE_URL", "").strip()
    )
    if not router_base:
        if os.getenv("OPENAI_API_KEY", "").strip() and not (
            os.getenv("ROUTERAI_API_KEY", "").strip()
            or os.getenv("ROUTER_API_KEY", "").strip()
        ):
            router_base = "https://api.openai.com/v1"
        else:
            router_base = "https://routerai.ru/api/v1"
    return Settings(
        bot_token=_need("BOT_TOKEN"),
        dadata_api_key=os.getenv("DADATA_API_KEY", "").strip(),
        region=os.getenv("REGION", "Татарстан").strip() or "Татарстан",
        city=os.getenv("CITY", "Казань").strip() or "Казань",
        db_path=data_dir / "niteos.db",
        webhook_url=os.getenv("WEBHOOK_URL", "").strip(),
        webhook_secret=os.getenv("WEBHOOK_SECRET", "").strip(),
        telegram_proxy=os.getenv("TELEGRAM_PROXY", "").strip(),
        webapp_url=os.getenv("WEBAPP_URL", "").strip(),
        webapp_port=int(os.getenv("WEBAPP_PORT", "8088") or 8088),
        webapp_token=webapp_token,
        webapp_password=os.getenv("WEBAPP_PASSWORD", "").strip(),
        session_secret=(
            os.getenv("SESSION_SECRET", "").strip() or webapp_token or "niteos-dev"
        ),
        router_api_key=router_key,
        router_base_url=router_base.rstrip("/"),
        router_model=(
            os.getenv("ROUTERAI_MODEL", "").strip()
            or os.getenv("ROUTER_MODEL", "").strip()
            or os.getenv("OPENAI_MODEL", "").strip()
            or "openai/gpt-4o-mini"
        ),
        allowed_user_ids=parse_allowed_user_ids(
            os.getenv("ALLOWED_USER_IDS", "").strip()
        ),
    )
