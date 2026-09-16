"""Run one local webapp hunt and print a compact card audit summary."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import load_settings


def _payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return payload if isinstance(payload, dict) else {}


def _presence_value(presence: dict[str, Any], key: str) -> str:
    item = presence.get(key)
    return str((item or {}).get("value") or "") if isinstance(item, dict) else ""


def _presence_status(presence: dict[str, Any], key: str) -> str:
    item = presence.get(key)
    return str((item or {}).get("status") or "") if isinstance(item, dict) else ""


def main() -> None:
    settings = load_settings()
    base = os.getenv("SMOKE_BASE", f"http://127.0.0.1:{settings.webapp_port}").rstrip("/")
    count = int(os.getenv("SMOKE_COUNT", "1") or "1")
    query = os.getenv("SMOKE_QUERY", "торговый центр")
    spheres = [
        item.strip()
        for item in os.getenv("SMOKE_SPHERES", "commercial").split(",")
        if item.strip()
    ]
    city = os.getenv("SMOKE_CITY", "Казань")
    region = os.getenv("SMOKE_REGION", "Татарстан")

    with httpx.Client(timeout=40.0, follow_redirects=True) as client:
        if settings.webapp_password:
            login = client.post(f"{base}/api/login", json={"password": settings.webapp_password})
            print("login", login.status_code, "ok" if login.status_code == 200 else login.text[:160], flush=True)
            login.raise_for_status()

        started = client.post(
            f"{base}/api/hunt",
            json={
                "phrase": "",
                "search_queries": [query],
                "spheres": spheres,
                "cities": [city],
                "regions": [region],
                "count": count,
                "okved": [],
            },
        )
        print("start", started.status_code, started.text[:220], flush=True)
        started.raise_for_status()
        hunt_id = int(started.json()["id"])

        data: dict[str, Any] = {}
        for idx in range(90):
            time.sleep(4)
            poll = client.get(f"{base}/api/hunt/{hunt_id}")
            poll.raise_for_status()
            data = poll.json()
            progress = str(data.get("progress") or "").replace("\n", " | ")[:240]
            print(f"poll{idx}", data.get("status"), progress, flush=True)
            if data.get("status") in {"done", "error"}:
                break

    payload = _payload(data)
    companies = payload.get("companies") or data.get("companies") or []
    print("summary", json.dumps({"hunt_id": hunt_id, "status": data.get("status"), "cards": len(companies)}, ensure_ascii=False), flush=True)
    for pos, company in enumerate(companies[:count], 1):
        obj = company.get("object") if isinstance(company.get("object"), dict) else {}
        presence = company.get("presence") if isinstance(company.get("presence"), dict) else {}
        relation = obj.get("relation") if isinstance(obj.get("relation"), dict) else {}
        photos = company.get("photos") if isinstance(company.get("photos"), list) else []
        people = company.get("people_contacts") if isinstance(company.get("people_contacts"), list) else []
        print(
            json.dumps(
                {
                    "n": pos,
                    "building": obj.get("title") or "",
                    "address": obj.get("address") or company.get("object_address") or "",
                    "company": company.get("name") or "",
                    "inn": company.get("inn") or "",
                    "relation": relation.get("status") or "",
                    "relation_confidence": relation.get("confidence"),
                    "photos": photos[:3],
                    "site": _presence_value(presence, "site"),
                    "site_status": _presence_status(presence, "site"),
                    "phone": _presence_value(presence, "phone"),
                    "phone_status": _presence_status(presence, "phone"),
                    "email": _presence_value(presence, "email"),
                    "people": people[:5],
                    "audit": company.get("card_audit") or {},
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
