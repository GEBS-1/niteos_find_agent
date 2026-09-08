"""Build Hunt Hub UI and deploy web + app to VPS."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def put_dir(sftp, local: Path, remote: str) -> None:
    try:
        sftp.mkdir(remote)
    except OSError:
        pass
    for path in local.iterdir():
        if path.name in {"__pycache__", "node_modules", ".git"} or path.suffix == ".pyc":
            continue
        dest = f"{remote}/{path.name}"
        if path.is_dir():
            put_dir(sftp, path, dest)
        else:
            sftp.put(str(path), dest)


def main() -> None:
    frontend = ROOT / "frontend"
    print("build frontend")
    subprocess.check_call(["npm", "run", "build"], cwd=str(frontend), shell=True)

    env = load_env()
    client = ssh_connect(env)
    sftp = client.open_sftp()
    print("upload app/web")
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    # Ensure remote assets dir exists / refresh
    try:
        sftp.mkdir("/opt/niteos/web/assets")
    except OSError:
        pass
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    sftp.close()

    code, text = run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; "
        "systemctl start niteos-bot; sleep 4; "
        "systemctl is-active niteos-bot; "
        "curl -sS -o /dev/null -w 'root=%{http_code}\\n' --max-time 8 http://127.0.0.1:8088/; "
        "curl -sS -o /dev/null -w 'assets_js=%{http_code}\\n' --max-time 8 "
        "$(python3 - <<'PY'\nfrom pathlib import Path\n"
        "html=Path('/opt/niteos/web/index.html').read_text()\n"
        "import re\nm=re.search(r'/assets/[^\"\\']+\\.js', html)\n"
        "print('http://127.0.0.1:8088'+(m.group(0) if m else '/'))\nPY\n)",
        timeout=90,
    )
    print(text)
    client.close()
    print("deploy_ui_done")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
