"""Finish MVP_1 deploy: fix venv (py3.12), install, build, start services."""
from __future__ import annotations

from sshutil import load_env, run, ssh_connect

REMOTE = "/opt/mvp_1"
API_PORT = 8089
WEB_PORT = 3020
PY = "/opt/niteos/.venv/bin/python"

API_SERVICE = f"""[Unit]
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

WEB_SERVICE = f"""[Unit]
Description=MVP_1 SaaS web (Next.js)
After=network.target mvp1-api.service

[Service]
Type=simple
WorkingDirectory={REMOTE}/saas_mvp
Environment=NODE_ENV=production
Environment=PORT={WEB_PORT}
Environment=HOSTNAME=127.0.0.1
ExecStart=/usr/bin/npm start -- -p {WEB_PORT} -H 127.0.0.1
Restart=on-failure
RestartSec=8

[Install]
WantedBy=multi-user.target
"""

TUNNEL_SERVICE = f"""[Unit]
Description=Cloudflare quick tunnel for MVP_1 web
After=network.target mvp1-web.service
Wants=mvp1-web.service

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


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())

    setup = f"""
set -e
pkill -f '{REMOTE}/.venv/bin/pip' || true
sleep 1
rm -rf {REMOTE}/.venv
{PY} -m venv {REMOTE}/.venv
{REMOTE}/.venv/bin/pip install --upgrade pip
{REMOTE}/.venv/bin/pip install -r {REMOTE}/api/requirements.txt
"""
    print("=== pip install (py3.12) ===")
    code, text = run(client, setup, timeout=1800)
    print(code, out(text)[-4000:])
    if code != 0:
        client.close()
        raise SystemExit("pip failed")

    patch = f"""
python3 - <<'PY'
from pathlib import Path
p = Path("{REMOTE}/saas_mvp/next.config.ts")
text = p.read_text(encoding="utf-8").replace("127.0.0.1:8000", "127.0.0.1:{API_PORT}")
p.write_text(text, encoding="utf-8")
p = Path("{REMOTE}/api/main.py")
text = p.read_text(encoding="utf-8")
old = '"web", "node_modules", "makehuman-data", "public", "data", "proxies", "clothes"'
new = '"saas_mvp", "public", "vendor", "makehuman-data", "data", "proxies", "clothes"'
if old in text:
    text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")
print("patched")
PY
"""
    run(client, patch, timeout=60)

    web = f"""
set -e
export NODE_OPTIONS=--max-old-space-size=512
cd {REMOTE}/saas_mvp
npm ci || npm install
npm run build
"""
    print("=== npm build ===")
    code, text = run(client, web, timeout=3600)
    print(code, out(text)[-5000:])
    if code != 0:
        print("WARN: web build failed")

    sftp = client.open_sftp()
    with sftp.file("/etc/systemd/system/mvp1-api.service", "w") as fh:
        fh.write(API_SERVICE)
    with sftp.file("/etc/systemd/system/mvp1-web.service", "w") as fh:
        fh.write(WEB_SERVICE)
    if run(client, "test -x /usr/local/bin/cloudflared", timeout=10)[0] == 0:
        with sftp.file("/etc/systemd/system/mvp1-tunnel.service", "w") as fh:
            fh.write(TUNNEL_SERVICE)
    sftp.close()

    boot = f"""
systemctl daemon-reload
systemctl enable mvp1-api.service
systemctl restart mvp1-api.service
sleep 3
systemctl is-active mvp1-api.service
curl -sS --max-time 15 http://127.0.0.1:{API_PORT}/ 
systemctl enable mvp1-web.service
systemctl restart mvp1-web.service
sleep 6
systemctl is-active mvp1-web.service || journalctl -u mvp1-web -n 20 --no-pager
curl -sS --max-time 20 -o /dev/null -w 'web:%{{http_code}}\\n' http://127.0.0.1:{WEB_PORT}/
if systemctl list-unit-files mvp1-tunnel.service >/dev/null 2>&1; then
  systemctl enable mvp1-tunnel.service
  systemctl restart mvp1-tunnel.service
  sleep 10
  grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' /opt/mvp_1/cloudflared.log | tail -1 || true
fi
ss -tlnp | grep -E '{API_PORT}|{WEB_PORT}' || true
df -h /
"""
    print("=== start services ===")
    code, text = run(client, boot, timeout=180)
    print(code, out(text))
    client.close()
    print("done")


if __name__ == "__main__":
    main()
