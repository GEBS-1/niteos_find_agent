from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from app.config import Settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    inn TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ogrn TEXT,
    okved TEXT,
    address TEXT,
    status TEXT,
    management TEXT,
    stamp TEXT,
    score INTEGER,
    idea TEXT,
    sphere TEXT,
    source TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS hunts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    phrase TEXT,
    spheres_json TEXT NOT NULL,
    okved TEXT,
    region TEXT,
    city TEXT,
    target_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hunt_results (
    hunt_id INTEGER NOT NULL,
    inn TEXT NOT NULL,
    skipped INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (hunt_id, inn)
);
CREATE TABLE IF NOT EXISTS share_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL UNIQUE,
    label TEXT,
    max_uses INTEGER NOT NULL DEFAULT 1,
    uses INTEGER NOT NULL DEFAULT 0,
    bound_ip TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def connect(settings: Settings) -> aiosqlite.Connection:
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.executescript(SCHEMA)
    await _migrate(db)
    await db.commit()
    return db


async def _migrate(db: aiosqlite.Connection) -> None:
    cur = await db.execute("PRAGMA table_info(hunts)")
    cols = {row[1] for row in await cur.fetchall()}
    if "region" not in cols:
        await db.execute("ALTER TABLE hunts ADD COLUMN region TEXT")
    if "city" not in cols:
        await db.execute("ALTER TABLE hunts ADD COLUMN city TEXT")
    if "progress" not in cols:
        await db.execute("ALTER TABLE hunts ADD COLUMN progress TEXT")
    if "result_json" not in cols:
        await db.execute("ALTER TABLE hunts ADD COLUMN result_json TEXT")
    cur = await db.execute("PRAGMA table_info(companies)")
    company_cols = {row[1] for row in await cur.fetchall()}
    if "kp_status" not in company_cols:
        await db.execute("ALTER TABLE companies ADD COLUMN kp_status TEXT")
    if "kp_at" not in company_cols:
        await db.execute("ALTER TABLE companies ADD COLUMN kp_at TEXT")
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS share_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE,
            label TEXT,
            max_uses INTEGER NOT NULL DEFAULT 1,
            uses INTEGER NOT NULL DEFAULT 0,
            bound_ip TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        )
        """
    )


async def create_share_link(
    db: aiosqlite.Connection,
    *,
    token: str,
    label: str = "",
    max_uses: int = 1,
    expires_at: str | None = None,
) -> int:
    await db.execute(
        """
        INSERT INTO share_links (token, label, max_uses, uses, bound_ip, expires_at, created_at, revoked)
        VALUES (?, ?, ?, 0, NULL, ?, ?, 0)
        """,
        (token, label or "", max(1, int(max_uses)), expires_at, _now()),
    )
    await db.commit()
    cur = await db.execute("SELECT last_insert_rowid() AS id")
    row = await cur.fetchone()
    return int(row["id"])


async def get_share_by_token(db: aiosqlite.Connection, token: str) -> dict | None:
    cur = await db.execute(
        "SELECT * FROM share_links WHERE token = ?",
        (token,),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def consume_share_link(
    db: aiosqlite.Connection,
    *,
    token: str,
    ip: str,
) -> dict | None:
    """Burn one use on first open. Link cannot be reused by another visitor."""
    row = await get_share_by_token(db, token)
    if not row or int(row.get("revoked") or 0):
        return None
    expires = str(row.get("expires_at") or "")
    if expires and expires < _now():
        return None
    uses = int(row.get("uses") or 0)
    max_uses = int(row.get("max_uses") or 1)
    # Strict one-time: after first successful enter the token is dead.
    # Returning guest relies on session cookie / X-Niteos-Session, not ?s= again.
    if uses >= max_uses:
        return None
    await db.execute(
        "UPDATE share_links SET bound_ip = ?, uses = uses + 1 WHERE id = ?",
        (ip or "unknown", row["id"]),
    )
    await db.commit()
    row["bound_ip"] = ip or "unknown"
    row["uses"] = uses + 1
    return row


async def revoke_share_link(db: aiosqlite.Connection, token: str) -> bool:
    cur = await db.execute(
        "UPDATE share_links SET revoked = 1 WHERE token = ?",
        (token,),
    )
    await db.commit()
    return cur.rowcount > 0


async def known_inns(db: aiosqlite.Connection) -> set[str]:
    cur = await db.execute("SELECT inn FROM companies")
    rows = await cur.fetchall()
    return {row["inn"] for row in rows}


async def kp_done_inns(db: aiosqlite.Connection) -> set[str]:
    """INNs that already went to KP — exclude from future hunts."""
    cur = await db.execute(
        """
        SELECT inn FROM companies
        WHERE lower(COALESCE(kp_status, '')) IN ('в кп', 'kp', 'done', 'sent', 'взято')
        """
    )
    rows = await cur.fetchall()
    return {row["inn"] for row in rows}


async def mark_company_kp(db: aiosqlite.Connection, inn: str) -> bool:
    """Mark company as taken into KP workflow — drops out of future hunts."""
    inn = (inn or "").strip()
    if not inn:
        return False
    now = _now()
    cur = await db.execute("SELECT inn, payload_json FROM companies WHERE inn = ?", (inn,))
    row = await cur.fetchone()
    if not row:
        return False
    payload: dict = {}
    try:
        payload = json.loads(row["payload_json"] or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    payload["kp_status"] = "в КП"
    payload["kp_at"] = now
    await db.execute(
        """
        UPDATE companies
        SET kp_status = ?, kp_at = ?, last_seen_at = ?, payload_json = ?
        WHERE inn = ?
        """,
        ("в КП", now, now, json.dumps(payload, ensure_ascii=False), inn),
    )
    await db.commit()
    return True


async def list_kp_companies(db: aiosqlite.Connection, *, limit: int = 50) -> list[dict]:
    """History of companies taken into КП, newest first."""
    cur = await db.execute(
        """
        SELECT inn, name, address, management, kp_status, kp_at, payload_json, last_seen_at
        FROM companies
        WHERE lower(COALESCE(kp_status, '')) IN ('в кп', 'kp', 'done', 'sent', 'взято')
        ORDER BY COALESCE(kp_at, last_seen_at) DESC
        LIMIT ?
        """,
        (max(1, min(int(limit), 200)),),
    )
    rows = await cur.fetchall()
    out: list[dict] = []
    for row in rows:
        payload: dict = {}
        try:
            payload = json.loads(row["payload_json"] or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        obj = payload.get("object") if isinstance(payload.get("object"), dict) else {}
        photos = payload.get("photos") or []
        if not isinstance(photos, list):
            photos = []
        out.append(
            {
                "inn": row["inn"],
                "name": row["name"] or payload.get("name") or "",
                "address": row["address"] or payload.get("address") or "",
                "management": row["management"] or payload.get("management") or "",
                "kp_status": row["kp_status"] or "в КП",
                "kp_at": row["kp_at"] or "",
                "object_title": (obj or {}).get("title") or "",
                "object_address": (obj or {}).get("address") or "",
                "photos": photos[:3],
                "phone": ((payload.get("presence") or {}).get("phone") or {}).get("value")
                if isinstance(payload.get("presence"), dict)
                else "",
            }
        )
    return out


async def company_count(db: aiosqlite.Connection) -> int:
    cur = await db.execute("SELECT COUNT(*) AS n FROM companies")
    row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def save_company(db: aiosqlite.Connection, company: dict) -> bool:
    """Insert if new. Returns True if inserted, False if inn already existed."""
    inn = company["inn"]
    now = _now()
    cur = await db.execute("SELECT inn FROM companies WHERE inn = ?", (inn,))
    exists = await cur.fetchone()
    if exists:
        await db.execute(
            "UPDATE companies SET last_seen_at = ? WHERE inn = ?",
            (now, inn),
        )
        await db.commit()
        return False
    await db.execute(
        """
        INSERT INTO companies (
            inn, name, ogrn, okved, address, status, management,
            stamp, score, idea, sphere, source, first_seen_at, last_seen_at, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            inn,
            company.get("name") or inn,
            company.get("ogrn"),
            company.get("okved"),
            company.get("address"),
            company.get("status"),
            company.get("management"),
            company.get("stamp"),
            company.get("score"),
            company.get("idea"),
            company.get("sphere"),
            company.get("source") or "dadata",
            now,
            now,
            json.dumps(company.get("payload") or {}, ensure_ascii=False),
        ),
    )
    await db.commit()
    return True


async def update_company(db: aiosqlite.Connection, inn: str, fields: dict) -> None:
    if not fields:
        return
    fields = {**fields, "last_seen_at": _now()}
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [inn]
    await db.execute(f"UPDATE companies SET {cols} WHERE inn = ?", values)
    await db.commit()


async def create_hunt(
    db: aiosqlite.Connection,
    user_id: int,
    phrase: str,
    spheres: list[str],
    okved: str,
    target_count: int,
    region: str = "",
    city: str = "",
    status: str = "running",
) -> int:
    cur = await db.execute(
        """
        INSERT INTO hunts (
            user_id, phrase, spheres_json, okved, region, city, target_count, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            phrase,
            json.dumps(spheres, ensure_ascii=False),
            okved,
            region,
            city,
            target_count,
            status,
            _now(),
        ),
    )
    await db.commit()
    return int(cur.lastrowid)


async def finish_hunt(
    db: aiosqlite.Connection,
    hunt_id: int,
    status: str,
    result: dict | None = None,
) -> None:
    if result is None:
        await db.execute("UPDATE hunts SET status = ? WHERE id = ?", (status, hunt_id))
    else:
        await db.execute(
            "UPDATE hunts SET status = ?, result_json = ? WHERE id = ?",
            (status, json.dumps(result, ensure_ascii=False), hunt_id),
        )
    await db.commit()


async def set_hunt_progress(db: aiosqlite.Connection, hunt_id: int, text: str) -> None:
    await db.execute(
        "UPDATE hunts SET progress = ?, status = CASE WHEN status = 'queued' THEN 'running' ELSE status END WHERE id = ?",
        (text, hunt_id),
    )
    await db.commit()


def _company_view(row: aiosqlite.Row | dict) -> dict:
    if isinstance(row, dict):
        get = row.get
    else:
        get = row.__getitem__
    return {
        "inn": get("inn"),
        "name": get("name"),
        "okved": get("okved"),
        "address": get("address"),
        "status": get("status"),
        "management": get("management"),
        "stamp": get("stamp"),
        "score": get("score"),
        "idea": get("idea"),
        "ogrn": get("ogrn"),
    }


async def get_hunt(db: aiosqlite.Connection, hunt_id: int) -> dict | None:
    cur = await db.execute("SELECT * FROM hunts WHERE id = ?", (hunt_id,))
    row = await cur.fetchone()
    if not row:
        return None
    payload = {
        "id": row["id"],
        "user_id": row["user_id"],
        "phrase": row["phrase"] or "",
        "spheres": json.loads(row["spheres_json"] or "[]"),
        "okved": row["okved"] or "",
        "region": row["region"] or "",
        "city": row["city"] or "",
        "target_count": row["target_count"],
        "status": row["status"],
        "progress": row["progress"] or "",
        "created_at": row["created_at"],
        "companies": [],
        "already": 0,
        "skipped": 0,
        "dropped": 0,
        "errors": [],
        "queries": [],
    }
    raw = row["result_json"] if "result_json" in row.keys() else None
    if raw:
        extra = json.loads(raw)
        payload.update({k: extra[k] for k in extra if k in payload or k == "companies"})
        payload["already"] = extra.get("already", 0)
        payload["skipped"] = extra.get("skipped", 0)
        payload["dropped"] = extra.get("dropped", 0)
        payload["errors"] = extra.get("errors") or []
        payload["queries"] = extra.get("queries") or []
        payload["companies"] = extra.get("companies") or []
        return payload
    cur = await db.execute(
        """
        SELECT c.* FROM hunt_results r
        JOIN companies c ON c.inn = r.inn
        WHERE r.hunt_id = ? AND r.skipped = 0
        """,
        (hunt_id,),
    )
    payload["companies"] = [_company_view(item) for item in await cur.fetchall()]
    return payload


async def fail_stale_hunts(db: aiosqlite.Connection, *, max_age_sec: int = 180) -> int:
    """Mark queued/running hunts older than max_age_sec as error so UI is not stuck."""
    cur = await db.execute(
        """
        SELECT id, created_at FROM hunts
        WHERE status IN ('queued', 'running')
        """
    )
    rows = await cur.fetchall()
    now = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    n = 0
    for row in rows:
        created = row["created_at"] or ""
        try:
            # ISO or sqlite timestamp
            raw = str(created).replace("Z", "+00:00")
            dt = __import__("datetime").datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=__import__("datetime").timezone.utc)
            age = (now - dt).total_seconds()
        except Exception:
            age = max_age_sec + 1
        if age >= max_age_sec:
            await db.execute(
                "UPDATE hunts SET status = 'error', progress = COALESCE(progress,'') || '\nСброс: зависла' WHERE id = ?",
                (row["id"],),
            )
            n += 1
    if n:
        await db.commit()
    return n


async def running_hunt_for_user(db: aiosqlite.Connection, user_id: int) -> int | None:
    await fail_stale_hunts(db, max_age_sec=180)
    cur = await db.execute(
        "SELECT id FROM hunts WHERE user_id = ? AND status IN ('queued', 'running') ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    row = await cur.fetchone()
    return int(row["id"]) if row else None


async def add_result(db: aiosqlite.Connection, hunt_id: int, inn: str, skipped: bool) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO hunt_results (hunt_id, inn, skipped) VALUES (?, ?, ?)",
        (hunt_id, inn, 1 if skipped else 0),
    )
    await db.commit()
