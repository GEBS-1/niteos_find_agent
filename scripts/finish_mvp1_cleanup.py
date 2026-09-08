from sshutil import load_env, run, ssh_connect

REMOTE = "/opt/mvp_1"
API_PORT = 8089
WEB_PORT = 3020

c = ssh_connect(load_env())

steps = [
    ("free disk", """
set -e
rm -rf /root/.npm /root/.cache/pip /root/.cache/uv /tmp/* /var/cache/apt/archives/*.deb
apt-get clean 2>/dev/null || true
{REMOTE}/.venv/bin/pip cache purge 2>/dev/null || true
journalctl --vacuum-size=50M 2>/dev/null || true
df -h /
""".replace("{REMOTE}", REMOTE)),
    ("clean broken node_modules", f"rm -rf {REMOTE}/saas_mvp/node_modules {REMOTE}/saas_mvp/.next; df -h /"),
    ("write api unit", None),
    ("start api", f"""
cat > /etc/systemd/system/mvp1-api.service <<'EOF'
[Unit]
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
EOF
systemctl daemon-reload
systemctl enable mvp1-api
systemctl restart mvp1-api
sleep 3
systemctl is-active mvp1-api
curl -sS http://127.0.0.1:{API_PORT}/
"""),
    ("npm install build", f"""
set -e
export NODE_OPTIONS=--max-old-space-size=384
cd {REMOTE}/saas_mvp
npm install --no-audit --no-fund
npm run build
df -h /
"""),
    ("start web+tunnel", f"""
cat > /etc/systemd/system/mvp1-web.service <<'EOF'
[Unit]
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
EOF
cat > /etc/systemd/system/mvp1-tunnel.service <<'EOF'
[Unit]
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
EOF
systemctl daemon-reload
systemctl enable mvp1-web mvp1-tunnel
systemctl restart mvp1-web
sleep 8
systemctl is-active mvp1-web || journalctl -u mvp1-web -n 20 --no-pager
curl -sS -o /dev/null -w 'web:%{{http_code}}\\n' http://127.0.0.1:{WEB_PORT}/
systemctl restart mvp1-tunnel
sleep 10
grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' /opt/mvp_1/cloudflared.log | tail -1 || true
ss -tlnp | grep -E '{API_PORT}|{WEB_PORT}' || true
"""),
]

for name, cmd in steps:
    print(f"\n===== {name} =====")
    if cmd is None:
        continue
    code, text = run(c, cmd, timeout=3600 if "npm" in name else 300)
    safe = text.encode("ascii", "replace").decode("ascii")
    print(safe[-8000:])
    print("exit", code)
    if code != 0 and name not in ("free disk",):
        if name == "npm install build":
            print("npm failed - check disk")
            break

c.close()
