"""Reset stuck hunts and run Kazan mall hunt via local API."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8093"
DB = ROOT / "data" / "niteos.db"


def reset_db() -> None:
    con = sqlite3.connect(DB)
    con.execute(
        "UPDATE hunts SET status='error' WHERE status IN ('running','queued')"
    )
    con.execute("DELETE FROM hunt_results")
    con.execute("DELETE FROM companies")
    con.commit()
    con.close()
    print("reset_ok", flush=True)


def main() -> None:
    reset_db()
    client = httpx.Client(timeout=30.0, follow_redirects=True)
    r = client.post(f"{BASE}/api/login", json={"password": "niteos-demo"})
    print("login", r.status_code, r.text, flush=True)
    r = client.post(
        f"{BASE}/api/hunt",
        json={
            "phrase": "",
            "search_queries": ["торговый центр"],
            "spheres": ["commercial"],
            "cities": ["Казань"],
            "regions": ["Татарстан"],
            "count": 5,
            "okved": [],
        },
    )
    print("start", r.status_code, r.text, flush=True)
    hunt_id = r.json()["id"]
    for i in range(90):
        time.sleep(5)
        data = client.get(f"{BASE}/api/hunt/{hunt_id}").json()
        status = data.get("status")
        prog = (data.get("progress") or "").replace("\n", " | ")[:200]
        print(f"poll{i}", status, prog, flush=True)
        if status not in {"done", "error"}:
            continue
        out = ROOT / "data" / "ui_hunt_result.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        payload = data.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        comps = payload.get("companies") or data.get("companies") or []
        print("companies", len(comps), flush=True)
        for n, cc in enumerate(comps[:5], 1):
            obj = cc.get("object") or {}
            presence = cc.get("presence") or {}
            vk = bool((presence.get("vk_company") or {}).get("value"))
            site = bool((presence.get("site") or {}).get("value"))
            print(
                n,
                "building=",
                obj.get("title"),
                "| company=",
                cc.get("name"),
                "| inn=",
                cc.get("inn"),
                "| photos=",
                len(cc.get("photos") or []),
                "| site=",
                site,
                "| vk=",
                vk,
                "| relation=",
                (obj.get("relation") or {}).get("status"),
                flush=True,
            )
        print("DONE", out, flush=True)
        return
    print("timeout", flush=True)


if __name__ == "__main__":
    main()
