from __future__ import annotations

import json
import sys

from sshutil import load_env, run, ssh_connect


def _remote_script(city: str, query: str, count: int) -> str:
    return f"""
import json
import time
import urllib.request

base = "http://127.0.0.1:8088"
payload = json.dumps({{"city": {city!r}, "query": {query!r}, "count": {count}}}, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(
    base + "/api/hunts",
    data=payload,
    headers={{"Content-Type": "application/json; charset=utf-8"}},
    method="POST",
)
hunt = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
status = {{}}
for _ in range(180):
    status = json.loads(
        urllib.request.urlopen(base + f"/api/hunts/{{hunt['id']}}", timeout=20)
        .read()
        .decode("utf-8")
    )
    if status.get("status") in {{"completed", "failed"}}:
        break
    time.sleep(0.5)
rows = json.loads(
    urllib.request.urlopen(base + f"/api/hunts/{{hunt['id']}}/results", timeout=20)
    .read()
    .decode("utf-8")
)
summary = []
for row in rows:
    obj = row.get("object") or {{}}
    company = row.get("company") or {{}}
    summary.append({{
        "object": obj.get("name"),
        "address": obj.get("address"),
        "provider": obj.get("source_provider"),
        "source": obj.get("source_url"),
        "photo": bool(obj.get("photo_url")),
        "cadastre": obj.get("cadastral_number"),
        "cadastreStatus": obj.get("cadastre_status"),
        "cadastreSource": obj.get("cadastre_source"),
        "owner": company.get("name"),
        "ownerInn": company.get("inn"),
        "peopleCandidates": len(row.get("people_candidates") or []),
        "actionablePeople": len(row.get("people") or []),
        "lighting": (row.get("lighting") or {{}}).get("score"),
        "verification": (row.get("verification") or {{}}).get("score"),
        "relation": row.get("relation_status"),
        "confidence": row.get("confidence"),
    }})
print(json.dumps({{
    "huntId": hunt.get("id"),
    "city": {city!r},
    "query": {query!r},
    "status": status.get("status"),
    "message": status.get("message"),
    "cards": len(rows),
    "results": summary,
}}, ensure_ascii=False, indent=2))
"""


def main() -> None:
    aliases = {
        "kazan": "Казань",
        "hotel": "отель",
        "warehouse": "складской комплекс",
        "business": "бизнес центр",
        "retail": "торговый центр",
        "industrial": "производственный комплекс",
    }
    city_arg = sys.argv[1] if len(sys.argv) > 1 else "kazan"
    query_arg = sys.argv[2] if len(sys.argv) > 2 else "hotel"
    city = aliases.get(city_arg, city_arg)
    query = aliases.get(query_arg, query_arg)
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    path = "/tmp/verify_hunt_v5_query.py"
    with sftp.file(path, "w") as f:
        f.write(_remote_script(city, query, count))
    sftp.close()
    code, text = run(client, f"cd /opt/niteos && .venv/bin/python {path}", timeout=180)
    print(text.encode("cp1251", "replace").decode("cp1251", "replace"))
    client.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
