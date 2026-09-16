from __future__ import annotations

import json

from sshutil import load_env, run, ssh_connect


REMOTE_SCRIPT = r"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8088"
CASES = [
    {"city": "Казань", "query": "складской комплекс", "count": 1, "must_have_owner": True},
    {"city": "Казань", "query": "отель", "count": 1, "must_have_owner": False},
    {"city": "Казань", "query": "бизнес центр", "count": 1, "must_have_owner": False},
]


def request_json(url, payload=None):
    if payload is None:
        return json.loads(urllib.request.urlopen(url, timeout=25).read().decode("utf-8"))
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8"))


def run_case(case):
    hunt = request_json(BASE + "/api/hunts", case)
    status = {}
    for _ in range(220):
        status = request_json(BASE + f"/api/hunts/{hunt['id']}")
        if status.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.5)
    rows = request_json(BASE + f"/api/hunts/{hunt['id']}/results")
    result = rows[0] if rows else {}
    obj = result.get("object") or {}
    company = result.get("company") or {}
    people = result.get("people") or []
    people_candidates = result.get("people_candidates") or []
    checks = {
        "card": bool(rows),
        "photo": bool(obj.get("photo_url")),
        "cadastre": bool(obj.get("cadastral_number")),
        "cadastre_source": bool(obj.get("cadastre_source")),
        "owner": bool(company.get("inn")),
        "people_candidates": bool(people_candidates),
        "actionable_people": bool(people),
        "direct_contacts": any(p.get("contacts") for p in people),
    }
    required = ["card", "photo"]
    if case.get("must_have_owner"):
        required += ["cadastre", "cadastre_source", "owner", "people_candidates", "actionable_people", "direct_contacts"]
    failures = [key for key in required if not checks.get(key)]
    return {
        "case": case,
        "hunt_id": hunt.get("id"),
        "status": status.get("status"),
        "message": status.get("message"),
        "object": obj.get("name"),
        "provider": obj.get("source_provider"),
        "cadastre": obj.get("cadastral_number"),
        "cadastre_source": obj.get("cadastre_source"),
        "owner": company.get("name"),
        "owner_inn": company.get("inn"),
        "people_candidates": len(people_candidates),
        "actionable_people": len(people),
        "checks": checks,
        "failures": failures,
        "passed": not failures and status.get("status") == "completed",
    }


providers = request_json(BASE + "/api/providers")
results = [run_case(case) for case in CASES]
print(json.dumps({
    "providers": providers,
    "overall_passed": all(x["passed"] for x in results),
    "results": results,
}, ensure_ascii=False, indent=2))
"""


def main() -> None:
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    path = "/tmp/self_check_hunt_v5.py"
    with sftp.file(path, "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    code, text = run(client, f"cd /opt/niteos && .venv/bin/python {path}", timeout=420)
    print(text.encode("cp1251", "replace").decode("cp1251", "replace"))
    client.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
