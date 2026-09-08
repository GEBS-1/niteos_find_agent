"""Password sessions + one-time client share links."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from aiohttp import web


STAFF_UID = 10
GUEST_UID_BASE = 100_000


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    import base64

    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def session_secret(settings) -> str:
    return (
        (getattr(settings, "session_secret", "") or "").strip()
        or (getattr(settings, "webapp_token", "") or "").strip()
        or (getattr(settings, "webapp_password", "") or "").strip()
        or "niteos-dev-secret"
    )


def sign_session(secret: str, payload: dict[str, Any]) -> str:
    body = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = _b64url(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_session(secret: str, token: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expect = _b64url(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        data = json.loads(_b64url_decode(body).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    exp = int(data.get("exp") or 0)
    if exp and exp < int(time.time()):
        return None
    return data


def make_staff_session(settings, *, hours: int = 72) -> str:
    now = int(time.time())
    return sign_session(
        session_secret(settings),
        {"role": "staff", "uid": STAFF_UID, "iat": now, "exp": now + hours * 3600},
    )


def make_guest_session(
    settings,
    *,
    share_id: int,
    hours: int = 24,
) -> str:
    now = int(time.time())
    return sign_session(
        session_secret(settings),
        {
            "role": "guest",
            "uid": GUEST_UID_BASE + int(share_id),
            "share_id": int(share_id),
            "iat": now,
            "exp": now + hours * 3600,
        },
    )


def set_session_cookie(
    response: web.Response,
    token: str,
    *,
    max_age: int = 72 * 3600,
    secure: bool = False,
) -> None:
    response.set_cookie(
        "niteos_session",
        token,
        max_age=max_age,
        httponly=True,
        samesite="Lax",
        secure=secure,
        path="/",
    )


def clear_session_cookie(response: web.Response) -> None:
    response.del_cookie("niteos_session", path="/")


def new_share_token() -> str:
    return secrets.token_urlsafe(24)


def password_ok(settings, password: str) -> bool:
    expected = (getattr(settings, "webapp_password", "") or "").strip()
    if not expected:
        return False
    return hmac.compare_digest(password.strip(), expected)
