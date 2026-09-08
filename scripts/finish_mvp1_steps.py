"""Step-by-step MVP1 finish deploy."""
from sshutil import load_env, run, ssh_connect

REMOTE = "/opt/mvp_1"
PY = "/opt/niteos/.venv/bin/python"
API_PORT = 8089
WEB_PORT = 3020


def step(client, name: str, cmd: str, timeout: int = 600) -> int:
    print(f"\n=== {name} ===")
    code, text = run(client, cmd, timeout=timeout)
    safe = text.encode("ascii", "replace").decode("ascii")
    print(safe[-6000:] if len(safe) > 6000 else safe)
    print(f"exit {code}")
    return code


def main() -> None:
    c = ssh_connect(load_env())
    step(c, "kill pip", "kill -9 1155337 1155426 2>/dev/null; pkill -9 -f 'mvp_1/.venv' || true", 30)
    step(c, "remove venv", f"rm -rf {REMOTE}/.venv", 60)
    code = step(c, "create venv py312", f"{PY} -m venv {REMOTE}/.venv && {REMOTE}/.venv/bin/python --version", 120)
    if code != 0:
        return
    code = step(
        c,
        "pip install",
        f"cd {REMOTE} && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r api/requirements.txt",
        1800,
    )
    if code != 0:
        return
    step(
        c,
        "patch paths",
        f"""python3 - <<'PY'
from pathlib import Path
p = Path("{REMOTE}/saas_mvp/next.config.ts")
p.write_text(p.read_text(encoding='utf-8').replace('127.0.0.1:8000','127.0.0.1:{API_PORT}'), encoding='utf-8')
p = Path("{REMOTE}/api/main.py")
t = p.read_text(encoding='utf-8')
old = '"web", "node_modules", "makehuman-data", "public", "data", "proxies", "clothes"'
new = '"saas_mvp", "public", "vendor", "makehuman-data", "data", "proxies", "clothes"'
if old in t: t = t.replace(old,new); p.write_text(t, encoding='utf-8')
print('ok')
PY""",
        60,
    )
    code = step(
        c,
        "npm build",
        f"export NODE_OPTIONS=--max-old-space-size=512; cd {REMOTE}/saas_mvp && (npm ci || npm install) && npm run build",
        3600,
    )
    if code != 0:
        print("web build failed, continuing api only")

    api_unit = f"""[Unit]
Description=MVP_1 Fitting Room API
After=network.target
[Service]
Type=simple
WorkingDirectory={REMOTE}
Environment=PYTHONUNBUFFERED=1
ExecStart={REMOTE}/.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port {API_PORT}
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
"""
    web_unit = f"""[Unit]
Description=MVP_1 SaaS web
After=network.target mvp1-api.service
[Service]
Type=simple
WorkingDirectory={REMOTE}/saas_mvp
Environment=NODE_ENV=production
Environment=PORT={WEB_PORT}
ExecStart=/usr/bin/npm start -- -p {WEB_PORT} -H 127.0.0.1
Restart=on-failure
RestartSec=8
[Install]
WantedBy=multi-user.target
"""
    tunnel_unit = f"""[Unit]
Description=MVP_1 cloudflared tunnel
After=network.target mvp1-web.service
[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:{WEB_PORT}
Restart=on-failure
RestartSec=8
StandardOutput=append:/opt/mvp_1/cloudflared.log
StandardError=append:/opt/mvp_1/cloudflared.log
[Install]
WantedBy=multi-user.target
"""
    sftp = c.open_sftp()
    for path, body in [
        ("/etc/systemd/system/mvp1-api.service", api_unit),
        ("/etc/systemd/system/mvp1-web.service", web_unit),
        ("/etc/systemd/system/mvp1-tunnel.service", tunnel_unit),
    ]:
        with sftp.file(path, "w") as fh:
            fh.write(body)
    sftp.close()

    step(
        c,
        "start",
        f"""systemctl daemon-reload
systemctl enable mvp1-api && systemctl restart mvp1-api
sleep 3 && systemctl is-active mvp1-api
curl -sS http://127.0.0.1:{API_PORT}/
systemctl enable mvp1-web && systemctl restart mvp1-web
sleep 8 && systemctl is-active mvp1-web || journalctl -u mvp1-web -n 15 --no-pager
curl -sS -o /dev/null -w 'web:%{{http_code}}\\n' http://127.0.0.1:{WEB_PORT}/
systemctl enable mvp1-tunnel && systemctl restart mvp1-tunnel
sleep 10 && grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' /opt/mvp_1/cloudflared.log | tail -1 || true
ss -tlnp | grep -E '{API_PORT}|{WEB_PORT}' || true""",
        180,
    )
    c.close()


if __name__ == "__main__":
    main()
