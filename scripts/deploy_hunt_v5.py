from __future__ import annotations

from pathlib import Path
import sys

from sshutil import ROOT, load_env, run, ssh_connect


LOCAL = ROOT / "hunt-v5"
REMOTE = "/opt/niteos"


def safe_print(text: str) -> None:
    enc = sys.stdout.encoding or "utf-8"
    print((text or "").encode(enc, "replace").decode(enc, "replace"))


def put_dir(sftp, local: Path, remote: str) -> None:
    try:
        sftp.mkdir(remote)
    except OSError:
        pass
    for path in local.iterdir():
        if path.name in {"__pycache__", ".pytest_cache"} or path.suffix in {".pyc", ".db"}:
            continue
        dest = f"{remote}/{path.name}"
        if path.is_dir():
            put_dir(sftp, path, dest)
        else:
            sftp.put(str(path), dest)


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    sftp = client.open_sftp()
    print("upload hunt-v5 app/tests/requirements")
    put_dir(sftp, LOCAL / "app", f"{REMOTE}/app")
    put_dir(sftp, LOCAL / "tests", f"{REMOTE}/tests")
    sftp.put(str(LOCAL / "requirements.txt"), f"{REMOTE}/requirements.txt")
    sftp.close()

    router_key = env.get("ROUTERAI_API_KEY") or env.get("ROUTER_API_KEY") or ""
    dadata_key = env.get("DADATA_API_KEY") or ""
    dadata_secret = env.get("DADATA_SECRET_KEY") or ""
    twogis_key = env.get("TWOGIS_API_KEY") or env.get("TWO_GIS_API_KEY") or ""
    yandex_maps_key = env.get("YANDEX_MAPS_API_KEY") or ""
    cadastre_url = env.get("CADASTRE_API_URL") or ""
    cadastre_key = env.get("CADASTRE_API_KEY") or ""
    sync_env = f"""
python3 - <<'PY'
from pathlib import Path
p = Path('/opt/niteos/.env')
text = p.read_text(encoding='utf-8') if p.exists() else ''
keys = {{}}
for ln in text.splitlines():
    if '=' in ln and not ln.strip().startswith('#'):
        k, v = ln.split('=', 1)
        keys[k.strip()] = v.strip()
keys['DEMO_MODE'] = '0'
keys['DATABASE_URL'] = 'sqlite:////opt/niteos/data/niteos_hunt_v5.db'
keys['SALES_HIDE_PEOPLE_WITHOUT_CONTACTS'] = '1'
keys['LLM_ENABLED'] = '1' if {bool(router_key)!r} else keys.get('LLM_ENABLED', '0')
if {router_key!r}:
    keys['ROUTERAI_API_KEY'] = {router_key!r}
    keys['ROUTER_API_KEY'] = {router_key!r}
    keys['ROUTERAI_BASE_URL'] = keys.get('ROUTERAI_BASE_URL') or 'https://routerai.ru/api/v1'
    keys['ROUTERAI_MODEL'] = keys.get('ROUTERAI_MODEL') or 'openai/gpt-4o-mini'
if {dadata_key!r}:
    keys['DADATA_API_KEY'] = {dadata_key!r}
if {dadata_secret!r}:
    keys['DADATA_SECRET_KEY'] = {dadata_secret!r}
if {twogis_key!r}:
    keys['TWOGIS_API_KEY'] = {twogis_key!r}
if {yandex_maps_key!r}:
    keys['YANDEX_MAPS_API_KEY'] = {yandex_maps_key!r}
if {cadastre_url!r}:
    keys['CADASTRE_API_URL'] = {cadastre_url!r}
if {cadastre_key!r}:
    keys['CADASTRE_API_KEY'] = {cadastre_key!r}
p.write_text('\\n'.join(f'{{k}}={{v}}' for k, v in keys.items()) + '\\n', encoding='utf-8')
print(
    'env_ok',
    'demo=' + keys['DEMO_MODE'],
    'llm=' + keys['LLM_ENABLED'],
    'dadata=' + str(bool(keys.get('DADATA_API_KEY'))),
    'twogis=' + str(bool(keys.get('TWOGIS_API_KEY'))),
    'cadastre_http=' + str(bool(keys.get('CADASTRE_API_URL'))),
)
PY
"""
    code, text = run(client, sync_env, timeout=20)
    safe_print(text.strip())
    if code:
        raise SystemExit(code)

    install = (
        "mkdir -p /opt/niteos/data; "
        "cd /opt/niteos; "
        "test -x .venv/bin/python || python3 -m venv .venv; "
        ".venv/bin/python -m ensurepip --upgrade || python3 -m ensurepip --upgrade; "
        ".venv/bin/python -m pip install --upgrade pip; "
        ".venv/bin/python -m pip install -r requirements.txt"
    )
    code, text = run(client, install, timeout=240)
    safe_print(text)
    if code:
        raise SystemExit(code)

    unit = """cat > /etc/systemd/system/niteos-bot.service <<'UNIT'
[Unit]
Description=Niteos Hunt V5 web app
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/niteos
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/niteos/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8088
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
"""
    code, text = run(client, unit, timeout=20)
    safe_print(text)
    if code:
        raise SystemExit(code)

    checks = (
        "systemctl daemon-reload; "
        "systemctl restart niteos-bot; "
        "sleep 4; "
        "systemctl is-active niteos-bot; "
        "curl -sS --max-time 12 http://127.0.0.1:8088/api/health; echo; "
        "curl -sS -o /dev/null -w 'root=%{http_code}\\n' --max-time 12 http://127.0.0.1:8088/"
    )
    code, text = run(client, checks, timeout=180)
    safe_print(text)
    if code:
        raise SystemExit(code)
    client.close()
    print("deploy_hunt_v5_done")


if __name__ == "__main__":
    main()
