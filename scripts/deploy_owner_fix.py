"""Deploy owner-search fix + favicon + sync RouterAI key."""
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


def main() -> None:
    env = load_env()
    key = env.get("ROUTERAI_API_KEY") or env.get("ROUTER_API_KEY") or ""
    if not key:
        raise SystemExit("No ROUTERAI_API_KEY in local .env")
    base = env.get("ROUTERAI_BASE_URL") or "https://routerai.ru/api/v1"
    model = env.get("ROUTERAI_MODEL") or "openai/gpt-4o-mini"

    client = ssh_connect(env)
    sftp = client.open_sftp()
    print("upload app/web")
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    sftp.close()

    sync = f"""
python3 - <<'PY'
from pathlib import Path
p = Path('/opt/niteos/.env')
text = p.read_text(encoding='utf-8') if p.exists() else ''
keys = {{}}
for ln in text.splitlines():
    if '=' in ln and not ln.strip().startswith('#'):
        k,v = ln.split('=',1)
        keys[k.strip()] = v.strip()
keys['ROUTERAI_API_KEY'] = {key!r}
keys['ROUTER_API_KEY'] = {key!r}
keys['ROUTERAI_BASE_URL'] = {base!r}
keys['ROUTERAI_MODEL'] = {model!r}
keys['HUNT_LLM_WEB'] = '0'
keys['HUNT_LLM_VERIFY'] = '0'
keys['HUNT_LLM_OWNER'] = '0'
p.write_text('\\n'.join(f'{{k}}={{v}}' for k,v in keys.items()) + '\\n', encoding='utf-8')
print('synced_router', bool(keys.get('ROUTERAI_API_KEY')), 'llm_web', keys.get('HUNT_LLM_WEB'))
PY
"""
    code, text = run(client, sync, timeout=20)
    print("env", (text or "").strip())

    code, text = run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; "
        "systemctl start niteos-bot; sleep 3; "
        "systemctl is-active niteos-bot; "
        "curl -sS -o /dev/null -w 'root=%{http_code}\\n' "
        "--max-time 8 http://127.0.0.1:8088/; "
        "cd /opt/niteos && PYTHONPATH=/opt/niteos .venv/bin/python -c "
        "\"from app.cost_guard import llm_web_enabled,llm_verify_enabled,llm_owner_enabled; "
        "print('web',llm_web_enabled(),'verify',llm_verify_enabled(),'owner',llm_owner_enabled())\"",
        timeout=50,
    )
    print("bot", (text or "").encode("ascii", "replace").decode())
    client.close()
    print("deploy_done")


if __name__ == "__main__":
    main()
