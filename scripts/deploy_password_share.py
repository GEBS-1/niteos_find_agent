"""Deploy Niteos app/web + set WEBAPP_PASSWORD. Never print hostnames."""
from __future__ import annotations

from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def put_dir(sftp, local: Path, remote: str) -> None:
    try:
        sftp.mkdir(remote)
    except OSError:
        pass
    for path in local.iterdir():
        if path.name == "__pycache__" or path.suffix == ".pyc":
            continue
        dest = f"{remote}/{path.name}"
        if path.is_dir():
            put_dir(sftp, path, dest)
        else:
            sftp.put(str(path), dest)


def scrub(text: str) -> str:
    """Strip host-like tokens from remote output."""
    import re

    text = text.encode("ascii", "replace").decode("ascii")
    text = re.sub(r"https?://[^\s\"']+", "[url]", text)
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[ip]", text)
    text = re.sub(r"[a-z0-9.-]+\.(trycloudflare|com|ru|net|org)\b", "[host]", text, flags=re.I)
    return text


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    sftp = client.open_sftp()
    print("upload app…")
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    print("upload web…")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    sftp.close()

    setup = r"""
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('/opt/niteos/.env')
text = p.read_text(encoding='utf-8') if p.exists() else ''
lines = [ln for ln in text.splitlines() if ln.strip()]
kv = {}
order = []
for ln in lines:
    if '=' not in ln or ln.lstrip().startswith('#'):
        order.append(('raw', ln))
        continue
    k, v = ln.split('=', 1)
    k = k.strip()
    kv[k] = v
    order.append(('kv', k))

def setk(k, v):
    kv[k] = v
    if not any(kind == 'kv' and key == k for kind, key in order):
        order.append(('kv', k))

setk('WEBAPP_PASSWORD', 'niteos-demo')
setk('WEBAPP_PORT', kv.get('WEBAPP_PORT') or '8088')
if not (kv.get('WEBAPP_TOKEN') or '').strip():
    setk('WEBAPP_TOKEN', secrets.token_hex(16))
if not (kv.get('SESSION_SECRET') or '').strip():
    setk('SESSION_SECRET', secrets.token_hex(16))

out = []
seen = set()
for kind, val in order:
    if kind == 'raw':
        out.append(val)
    else:
        if val in seen:
            continue
        seen.add(val)
        out.append(f'{val}={kv[val]}')
for k, v in kv.items():
    if k not in seen:
        out.append(f'{k}={v}')
p.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
print('env_password_set')
print('token_ok' if kv.get('WEBAPP_TOKEN') else 'token_missing')
print('session_ok' if kv.get('SESSION_SECRET') else 'session_missing')
PY
"""
    code, text = run(client, setup, timeout=60)
    print("env", code, scrub(text)[-500:])

    restart = (
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; "
        "systemctl start niteos-bot; sleep 5; "
        "systemctl is-active niteos-bot; "
        "curl -sS -o /dev/null -w 'root=%{http_code}\\n' --max-time 8 http://127.0.0.1:8088/; "
        "curl -sS --max-time 8 http://127.0.0.1:8088/api/auth; echo; "
        "curl -sS --max-time 8 -X POST -H 'Content-Type: application/json' "
        "-d '{\"password\":\"niteos-demo\"}' -c /tmp/niteos_cj -b /tmp/niteos_cj "
        "http://127.0.0.1:8088/api/login; echo; "
        "curl -sS --max-time 8 -b /tmp/niteos_cj http://127.0.0.1:8088/api/auth; echo; "
        "curl -sS --max-time 8 -X POST -H 'Content-Type: application/json' "
        "-d '{\"label\":\"client\",\"max_uses\":1}' -b /tmp/niteos_cj "
        "http://127.0.0.1:8088/api/share/create | python3 -c "
        "\"import sys,json; d=json.load(sys.stdin); print('share_ok', bool(d.get('ok')), 'has_token', bool(d.get('token')))\""
    )
    code, text = run(client, restart, timeout=90)
    print("restart", code)
    print(scrub(text)[-1200:])
    client.close()
    print("deploy_done")


if __name__ == "__main__":
    main()
