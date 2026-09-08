from __future__ import annotations

import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qsl

log = logging.getLogger(__name__)


def parse_init_data(init_data: str, bot_token: str) -> dict:
    if not init_data:
        raise ValueError("нет initData")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True, encoding="utf-8"))
    received = parsed.pop("hash", "")
    if not received:
        raise ValueError("нет hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise ValueError("подписи нет")
    user_raw = parsed.get("user") or "{}"
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise ValueError("user битый") from exc
    user_id = int(user.get("id") or 0)
    if not user_id:
        raise ValueError("нет user id")
    return {"user_id": user_id, "user": user}
