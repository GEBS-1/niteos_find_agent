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


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    env = load_env()
    allowed = env.get("ALLOWED_USER_IDS", "").strip()
    client = ssh_connect(env)
    sftp = client.open_sftp()
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
    ln = ln.strip()
    if not ln or ln.startswith('#') or '=' not in ln:
        continue
    k,v = ln.split('=',1)
    keys[k.strip()] = v.strip()
keys.pop('ALLOWED_USER_IDS', None)
if {allowed!r}:
    keys['ALLOWED_USER_IDS'] = {allowed!r}
p.write_text('\\n'.join(f'{{k}}={{v}}' for k,v in keys.items()) + '\\n', encoding='utf-8')
print('allowed', keys.get('ALLOWED_USER_IDS', '(open)'))
PY
"""
    code, text = run(client, sync, timeout=20)
    print("env", code, out(text))
    code, text = run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; systemctl start niteos-bot; "
        "sleep 2; systemctl is-active niteos-bot; "
        "cd /opt/niteos && .venv/bin/python -c \"from app.config import load_settings; s=load_settings(); print('ids', sorted(s.allowed_user_ids))\"",
        timeout=40,
    )
    print("bot", code, out(text)[-500:])
    client.close()


if __name__ == "__main__":
    main()
