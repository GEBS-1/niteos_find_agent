"""Verify the deployed NITEOS webapp on the VPS without printing secrets."""
from __future__ import annotations

from sshutil import load_env, run, ssh_connect


VERIFY = r"""cd /opt/niteos && .venv/bin/python - <<'PY'
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8088"


def req(path, payload=None, cookie=""):
    data = None
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["X-Niteos-Session"] = cookie
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, headers=headers)
    with urllib.request.urlopen(r, timeout=25) as response:
        body = response.read().decode("utf-8", "replace")
        return response, json.loads(body) if body else {}


print("service", end=" ")
print(open("/proc/uptime", encoding="utf-8").read().split()[0])

env = {}
for line in open("/opt/niteos/.env", encoding="utf-8", errors="replace"):
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.rstrip("\n").split("=", 1)
        env[key.strip()] = value.strip()

session = ""
if env.get("WEBAPP_PASSWORD"):
    _, login = req("/api/login", {"password": env["WEBAPP_PASSWORD"]})
    session = str(login.get("session") or "")
    print("login", "ok" if session else "no_session")

meta_response, meta = req("/api/meta", cookie=session)
print("meta", meta_response.status, "spheres", len(meta.get("spheres") or []))

try:
    started_response, started = req(
        "/api/hunt",
        {
            "phrase": "",
            "search_queries": ["гостиница"],
            "spheres": ["commercial"],
            "cities": ["Казань"],
            "regions": ["Татарстан"],
            "count": 1,
            "okved": [],
        },
        cookie=session,
    )
except urllib.error.HTTPError as exc:
    if exc.code != 401:
        raise
    print("hunt_auth", "required")
    raise SystemExit(0)

print("hunt_start", started_response.status, started)
hid = int(started["id"])
data = {}
for i in range(75):
    time.sleep(4)
    _, data = req(f"/api/hunt/{hid}", cookie=session)
    progress = str(data.get("progress") or "").replace("\n", " | ")[:120]
    print("poll", i, data.get("status"), progress)
    if data.get("status") in {"done", "error"}:
        break

companies = data.get("companies") or []
print("hunt_done", data.get("status"), "cards", len(companies))
for c in companies[:1]:
    obj = c.get("object") if isinstance(c.get("object"), dict) else {}
    presence = c.get("presence") if isinstance(c.get("presence"), dict) else {}
    relation = obj.get("relation") if isinstance(obj.get("relation"), dict) else {}
    photos = c.get("photos") if isinstance(c.get("photos"), list) else []
    people = c.get("people_contacts") if isinstance(c.get("people_contacts"), list) else []
    owners = c.get("owner_candidates") if isinstance(c.get("owner_candidates"), list) else []
    lighting = c.get("lighting") if isinstance(c.get("lighting"), dict) else {}
    def presence_value(key):
        item = presence.get(key)
        return str((item or {}).get("value") or "") if isinstance(item, dict) else ""
    print(json.dumps({
        "building": obj.get("title") or c.get("name") or "",
        "address": obj.get("address") or c.get("object_address") or "",
        "inn": c.get("inn") or "",
        "relation": relation.get("status") or "",
        "relation_confidence": relation.get("confidence"),
        "photos": len(photos),
        "site": presence_value("site"),
        "phone": presence_value("phone"),
        "people": len(people),
        "owner_candidates": len(owners),
        "lighting": lighting,
        "audit": c.get("card_audit") or {},
    }, ensure_ascii=False))
PY"""


def main() -> None:
    client = ssh_connect(load_env())
    try:
        for cmd in [
            "systemctl is-active niteos-bot",
            "curl -sS -o /dev/null -w 'root=%{http_code}\\n' --max-time 8 http://127.0.0.1:8088/",
            "cd /opt/niteos && .venv/bin/python -m compileall app",
            "cd /opt/niteos && .venv/bin/python -m unittest discover tests",
            VERIFY,
            "journalctl -u niteos-bot -n 40 --no-pager -o cat",
        ]:
            code, text = run(client, cmd, timeout=360)
            print(f"=== {cmd.splitlines()[0][:90]} ===")
            print("exit", code)
            print(text[-6000:])
            if code != 0:
                raise SystemExit(code)
    finally:
        client.close()


if __name__ == "__main__":
    main()
