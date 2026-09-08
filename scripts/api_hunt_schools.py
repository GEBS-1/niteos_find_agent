"""Run Kazan schools hunt via local API and print card quality."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8095"
DB = ROOT / "data" / "niteos.db"
OUT = ROOT / "data" / "school_hunt_result.json"
LOG = ROOT / "data" / "school_hunt_eval.log"
COUNT = 3


def reset_stuck() -> None:
    con = sqlite3.connect(DB)
    con.execute(
        "UPDATE hunts SET status='error' WHERE status IN ('running','queued')"
    )
    con.commit()
    con.close()
    print("reset_stuck_ok", flush=True)


def log(line: str) -> None:
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def summarize(comps: list[dict]) -> None:
    log(f"=== CARDS {len(comps)} ===")
    for n, cc in enumerate(comps, 1):
        obj = cc.get("object") or {}
        presence = cc.get("presence") or {}
        rel = obj.get("relation") or {}
        vk = (presence.get("vk_company") or {}).get("value") or ""
        site = (presence.get("site") or {}).get("value") or ""
        phone = (presence.get("phone") or {}).get("value") or ""
        photos = cc.get("photos") or []
        checks = [
            f"building={obj.get('title') or '-'}",
            f"addr={obj.get('address') or '-'}",
            f"company={cc.get('name') or '-'}",
            f"inn={cc.get('inn') or '-'}",
            f"rel={rel.get('status') or '-'}@{rel.get('confidence') or 0}",
            f"photos={len(photos)}",
            f"site={'yes' if site else 'no'}",
            f"vk={'yes' if vk else 'no'}",
            f"phone={'yes' if phone else 'no'}",
        ]
        log(f"{n}. " + " | ".join(checks))
        if site:
            log(f"   site: {site}")
        if vk:
            log(f"   vk: {vk}")
        if rel.get("reason"):
            log(f"   reason: {str(rel.get('reason'))[:180]}")


def main() -> None:
    if LOG.exists():
        LOG.unlink()
    reset_stuck()
    client = httpx.Client(timeout=30.0, follow_redirects=True)
    r = client.post(f"{BASE}/api/login", json={"password": "niteos-demo"})
    log(f"login {r.status_code} {r.text[:120]}")
    r = client.post(
        f"{BASE}/api/hunt",
        json={
            "phrase": "",
            "search_queries": ["школа"],
            "spheres": ["social"],
            "cities": ["Казань"],
            "regions": ["Татарстан"],
            "count": COUNT,
            "okved": [],
        },
    )
    log(f"start {r.status_code} {r.text[:200]}")
    hunt_id = r.json()["id"]
    log(f"hunt_id={hunt_id}")
    for i in range(120):
        time.sleep(5)
        data = client.get(f"{BASE}/api/hunt/{hunt_id}").json()
        status = data.get("status")
        prog = (data.get("progress") or "").replace("\n", " | ")[:220]
        log(f"poll{i} {status} {prog}")
        if status not in {"done", "error"}:
            continue
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        payload = data.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        comps = payload.get("companies") or data.get("companies") or []
        summarize(comps if isinstance(comps, list) else [])
        log(f"DONE status={status} file={OUT}")
        return
    log("timeout")


if __name__ == "__main__":
    main()
