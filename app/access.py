from __future__ import annotations

from app.config import Settings


def parse_allowed_user_ids(raw: str) -> frozenset[int]:
    out: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return frozenset(out)


def access_enabled(settings: Settings) -> bool:
    return bool(settings.allowed_user_ids)


def is_allowed(settings: Settings, user_id: int) -> bool:
    """Пустой ALLOWED_USER_IDS — доступ у всех. Список задан — только эти ID."""
    if not settings.allowed_user_ids:
        return True
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    return uid in settings.allowed_user_ids


DENY_TEXT = (
    "Доступ только для команды Нитеос.\n"
    "Если ты из команды — пришли админу свой ID: /id"
)
