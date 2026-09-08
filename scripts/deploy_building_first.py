"""Deploy building-first fixes. Never print hostnames."""
from __future__ import annotations

from sshutil import ROOT, load_env, run, ssh_connect


def put_dir(sftp, local, remote: str) -> None:
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
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    print("upload app")
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    print("upload web")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    sftp.close()
    code, text = run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; "
        "systemctl start niteos-bot; sleep 4; "
        "systemctl is-active niteos-bot; "
        "curl -sS -o /dev/null -w 'root=%{http_code}\\n' --max-time 8 http://127.0.0.1:8088/",
        timeout=60,
    )
    print(text.strip())
    print("deploy_ok" if code == 0 else "deploy_fail")
    client.close()


if __name__ == "__main__":
    main()
