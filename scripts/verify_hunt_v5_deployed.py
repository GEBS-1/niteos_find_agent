from __future__ import annotations

import json
from pathlib import Path

from sshutil import load_env, run, ssh_connect


REMOTE_SCRIPT = r"""
import json
import time
import urllib.request

base = "http://127.0.0.1:8088"
payload = json.dumps({"city": "Казань", "query": "отель", "count": 1}).encode("utf-8")
req = urllib.request.Request(
    base + "/api/hunts",
    data=payload,
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)
hunt = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
status = {}
for _ in range(180):
    status = json.loads(
        urllib.request.urlopen(base + f"/api/hunts/{hunt['id']}", timeout=20)
        .read()
        .decode("utf-8")
    )
    if status.get("status") in {"completed", "failed"}:
        break
    time.sleep(0.5)
rows = json.loads(
    urllib.request.urlopen(base + f"/api/hunts/{hunt['id']}/results", timeout=20)
    .read()
    .decode("utf-8")
)
r = rows[0] if rows else {}
obj = r.get("object") or {}
company = r.get("company") or {}
print(json.dumps({
    "huntId": hunt.get("id"),
    "status": status.get("status"),
    "message": status.get("message"),
    "cards": len(rows),
    "object": obj.get("name"),
    "address": obj.get("address"),
    "provider": obj.get("source_provider"),
    "source": obj.get("source_url"),
    "photo": bool(obj.get("photo_url")),
    "owner": company.get("name"),
    "ownerInn": company.get("inn"),
    "peopleCandidates": len(r.get("people_candidates") or []),
    "actionablePeople": len(r.get("people") or []),
    "lighting": (r.get("lighting") or {}).get("score"),
    "verification": (r.get("verification") or {}).get("score"),
}, ensure_ascii=False, indent=2))
"""


def main() -> None:
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    path = "/tmp/verify_hunt_v5_deployed.py"
    with sftp.file(path, "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    code, text = run(client, f"cd /opt/niteos && .venv/bin/python {path}", timeout=180)
    print(text.encode("cp1251", "replace").decode("cp1251", "replace"))
    client.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
