"""Deploy auto-sync WebApp URL (no manual refresh after cloudflared restart)."""
from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

SYNC_TIMER = """[Unit]
Description=Sync Niteos WebApp URL from Cloudflare edge log
Requires=niteos-https-tunnel.service
After=niteos-https-tunnel.service

[Timer]
OnBootSec=30
OnUnitActiveSec=2min
Persistent=true

[Install]
WantedBy=timers.target
"""

SYNC_SERVICE = """[Unit]
Description=Sync Niteos WebApp URL from bypass Cloudflare log
After=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/niteos/scripts/sync_webapp_url.sh
"""


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
    try:
        sftp.mkdir("/opt/niteos/scripts")
    except OSError:
        pass
    sftp.put(str(ROOT / "scripts" / "sync_webapp_url.sh"), "/opt/niteos/scripts/sync_webapp_url.sh")
    sftp.close()

    run(client, "sed -i 's/\\r$//' /opt/niteos/scripts/sync_webapp_url.sh", timeout=10)
    run(client, "chmod +x /opt/niteos/scripts/sync_webapp_url.sh", timeout=10)

    for path, content in [
        ("/etc/systemd/system/niteos-sync-webapp.service", SYNC_SERVICE),
        ("/etc/systemd/system/niteos-sync-webapp.timer", SYNC_TIMER),
    ]:
        sftp = client.open_sftp()
        with sftp.file(path, "w") as fh:
            fh.write(content)
        sftp.close()

    cmds = [
        "systemctl daemon-reload",
        "systemctl enable --now niteos-sync-webapp.timer",
        "/opt/niteos/scripts/sync_webapp_url.sh || true",
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; systemctl start niteos-bot; sleep 4; systemctl is-active niteos-bot",
        "grep ^WEBAPP_URL= /opt/niteos/.env",
        "journalctl -u niteos-bot -n 15 --no-pager -o cat",
    ]
    for cmd in cmds:
        print("===", cmd[:70])
        code, text = run(client, cmd, timeout=60)
        print(code, out(text)[-1500:])

    client.close()
    print("DONE")


if __name__ == "__main__":
    main()
