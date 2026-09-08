"""Deploy MVP_1 (fitting room) parallel to Niteos on separate ports."""
from __future__ import annotations

import tarfile
import tempfile
from pathlib import Path

from sshutil import load_env, run, ssh_connect

MVP_ROOT = Path(r"D:\Python\Github\MVP_1")
REMOTE = "/opt/mvp_1"
API_PORT = 8089
WEB_PORT = 3020

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".next",
    "third_party",
    "makehuman_folder",
}
SKIP_SUFFIX = {".pyc", ".pyo"}


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def should_skip(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & SKIP_DIRS:
        return True
    if "api" in parts and "output" in parts:
        return True
    if rel.as_posix().startswith("api/output"):
        return True
    if rel.suffix.lower() in SKIP_SUFFIX:
        return True
    return False


def build_tarball() -> Path:
    tmp = Path(tempfile.gettempdir()) / "mvp1_deploy.tgz"
    print(f"packing {MVP_ROOT} -> {tmp}")
    count = 0
    with tarfile.open(tmp, "w:gz") as tar:
        for path in MVP_ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(MVP_ROOT)
            if should_skip(rel):
                continue
            tar.add(path, arcname=str(rel).replace("\\", "/"))
            count += 1
            if count % 500 == 0:
                print(f"  packed {count} files...")
    print(f"packed {count} files, size {tmp.stat().st_size / 1024 / 1024:.1f} MB")
    return tmp


def upload_tar(client, tar_path: Path) -> None:
    sftp = client.open_sftp()
    remote_tar = "/tmp/mvp1_deploy.tgz"
    print("uploading tarball...")
    sftp.put(str(tar_path), remote_tar)
    sftp.close()
    code, text = run(
        client,
        f"mkdir -p {REMOTE} && rm -rf {REMOTE}/* && "
        f"tar -xzf {remote_tar} -C {REMOTE} && rm -f {remote_tar} && "
        f"du -sh {REMOTE}",
        timeout=600,
    )
    print("extract", code, out(text)[-500:])


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


def patch_next_config(client) -> None:
    """Point Next rewrites to MVP API port on server."""
    script = f"""
python3 - <<'PY'
from pathlib import Path
p = Path("{REMOTE}/saas_mvp/next.config.ts")
text = p.read_text(encoding="utf-8")
text = text.replace("127.0.0.1:8000", "127.0.0.1:{API_PORT}")
p.write_text(text, encoding="utf-8")
print("patched next.config.ts")
PY
"""
    run(client, script, timeout=60)


def patch_api_paths(client) -> None:
    """Use saas_mvp vendor assets instead of web/node_modules on server."""
    script = f"""
python3 - <<'PY'
from pathlib import Path
p = Path("{REMOTE}/api/main.py")
text = p.read_text(encoding="utf-8")
old = '"web", "node_modules", "makehuman-data", "public", "data", "proxies", "clothes"'
new = '"saas_mvp", "public", "vendor", "makehuman-data", "data", "proxies", "clothes"'
if old in text:
    text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")
    print("patched api/main.py web proxies path")
else:
    print("api/main.py already patched or pattern missing")
PY
"""
    run(client, script, timeout=60)


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


def setup_server(client) -> None:
    cmds = [
        f"mkdir -p {REMOTE}/api/output {REMOTE}/data",
        f"test -x {REMOTE}/.venv/bin/python || /opt/niteos/.venv/bin/python -m venv {REMOTE}/.venv",
        f"cd {REMOTE} && .venv/bin/pip install --upgrade pip",
        f"cd {REMOTE} && .venv/bin/pip install -r api/requirements.txt",
    ]
    for cmd in cmds:
        print(">", cmd[:80])
        code, text = run(client, cmd, timeout=1800)
        print(code, out(text)[-2000:])
        if code != 0 and "pip install -r" in cmd:
            raise SystemExit("pip install failed")

    patch_next_config(client)
    patch_api_paths(client)

    sftp = client.open_sftp()
    with sftp.file("/etc/systemd/system/mvp1-api.service", "w") as fh:
        fh.write(API_SERVICE)
    with sftp.file("/etc/systemd/system/mvp1-web.service", "w") as fh:
        fh.write(WEB_SERVICE)
    if run(client, "test -x /usr/local/bin/cloudflared", timeout=10)[0] == 0:
        with sftp.file("/etc/systemd/system/mvp1-tunnel.service", "w") as fh:
            fh.write(TUNNEL_SERVICE)
    sftp.close()

    web_setup = f"""
set -e
export NODE_OPTIONS=--max-old-space-size=512
cd {REMOTE}/saas_mvp
if ! command -v npm >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nodejs npm
fi
npm ci || npm install
npm run build
"""
    print("building web...")
    code, text = run(client, web_setup, timeout=3600)
    print("web build", code, out(text)[-3000:])
    if code != 0:
        print("WARN: web build failed — API may still work")

    boot = f"""
systemctl daemon-reload
systemctl enable mvp1-api.service
systemctl restart mvp1-api.service
sleep 3
systemctl is-active mvp1-api.service
curl -sS --max-time 15 http://127.0.0.1:{API_PORT}/ || true
curl -sS --max-time 15 http://127.0.0.1:{API_PORT}/api/templates?for_web=1 | head -c 200 || true
systemctl enable mvp1-web.service
systemctl restart mvp1-web.service
sleep 5
systemctl is-active mvp1-web.service || true
curl -sS --max-time 15 -o /dev/null -w 'web:%{{http_code}}\\n' http://127.0.0.1:{WEB_PORT}/ || true
if systemctl list-unit-files mvp1-tunnel.service >/dev/null 2>&1; then
  systemctl enable mvp1-tunnel.service
  systemctl restart mvp1-tunnel.service
  sleep 8
  grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' /opt/mvp_1/cloudflared.log | tail -1 || true
fi
ss -tlnp | grep -E '{API_PORT}|{WEB_PORT}' || true
df -h /
"""
    code, text = run(client, boot, timeout=180)
    print("boot", code, out(text))


def main() -> None:
    if not MVP_ROOT.is_dir():
        raise SystemExit(f"MVP_1 not found: {MVP_ROOT}")
    tar_path = build_tarball()
    client = ssh_connect(load_env())
    try:
        upload_tar(client, tar_path)
        setup_server(client)
    finally:
        client.close()
        try:
            tar_path.unlink()
        except OSError:
            pass
    print("done")
    print(f"MVP API: http://127.0.0.1:{API_PORT}/ (on VPS)")
    print(f"MVP Web: http://127.0.0.1:{WEB_PORT}/ (on VPS)")


if __name__ == "__main__":
    main()
