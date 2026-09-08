from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import aiosqlite
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

SCHEMA = """
CREATE TABLE IF NOT EXISTS fsm (
    k TEXT PRIMARY KEY,
    state TEXT,
    data TEXT NOT NULL DEFAULT '{}'
);
"""


def _key(key: StorageKey) -> str:
    return ":".join(
        str(x)
        for x in (
            key.bot_id,
            key.chat_id,
            key.user_id,
            getattr(key, "thread_id", None) or 0,
            getattr(key, "business_connection_id", None) or 0,
            getattr(key, "destiny", None) or "default",
        )
    )


class SqliteStorage(BaseStorage):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self._path)
            await self._db.execute("PRAGMA journal_mode=WAL;")
            await self._db.executescript(SCHEMA)
            await self._db.commit()
        return self._db

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        db = await self._conn()
        value = state.state if hasattr(state, "state") else state
        await db.execute(
            """
            INSERT INTO fsm (k, state, data) VALUES (?, ?, '{}')
            ON CONFLICT(k) DO UPDATE SET state = excluded.state
            """,
            (_key(key), value),
        )
        await db.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        db = await self._conn()
        cur = await db.execute("SELECT state FROM fsm WHERE k = ?", (_key(key),))
        row = await cur.fetchone()
        return row[0] if row and row[0] else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        db = await self._conn()
        payload = json.dumps(dict(data), ensure_ascii=False)
        await db.execute(
            """
            INSERT INTO fsm (k, state, data) VALUES (?, NULL, ?)
            ON CONFLICT(k) DO UPDATE SET data = excluded.data
            """,
            (_key(key), payload),
        )
        await db.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        db = await self._conn()
        cur = await db.execute("SELECT data FROM fsm WHERE k = ?", (_key(key),))
        row = await cur.fetchone()
        if not row or not row[0]:
            return {}
        parsed = json.loads(row[0])
        return parsed if isinstance(parsed, dict) else {}

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
