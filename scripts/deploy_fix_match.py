from sshutil import ROOT, load_env, run, ssh_connect
from pathlib import Path


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
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    for name in ("run_demo_hunt.py", "test_smb_lpr.py", "test_vk_kp.py"):
        sftp.put(str(ROOT / "scripts" / name), f"/opt/niteos/scripts/{name}")
    sftp.close()

    code, text = run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; systemctl start niteos-bot; "
        "sleep 2; systemctl is-active niteos-bot",
        timeout=40,
    )
    print("bot", code, out(text)[-80:])

    code, text = run(
        client,
        "cd /opt/niteos && .venv/bin/python scripts/test_vk_kp.py",
        timeout=600,
    )
    print("test_vk_kp", code)
    print(out(text)[-8000:])

    code, text = run(
        client,
        "cd /opt/niteos && .venv/bin/python scripts/run_demo_hunt.py",
        timeout=1200,
    )
    print("demo_hunt", code)
    print(out(text)[-15000:])

    code2, text2 = run(client, "cat /tmp/niteos_demo_hunt.json", timeout=20)
    if code2 == 0:
        print("--- JSON summary ---")
        print(out(text2)[-6000:])
    client.close()
    print("done")


if __name__ == "__main__":
    main()
