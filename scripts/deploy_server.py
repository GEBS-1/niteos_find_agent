from __future__ import annotations

from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

REMOTE = "/opt/niteos"
UPLOAD_FILES = [
    "requirements.txt",
]
UPLOAD_DIRS = [
    "app",
]


def put_dir(sftp, local: Path, remote: str) -> None:
    try:
        sftp.mkdir(remote)
    except OSError:
        pass
    for path in local.iterdir():
        if path.name in {"__pycache__", ".pyc"} or path.suffix == ".pyc":
            continue
        dest = f"{remote}/{path.name}"
        if path.is_dir():
            put_dir(sftp, path, dest)
        else:
            sftp.put(str(path), dest)


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    print("connected")

    for cmd in [
        "apt-get clean",
        "journalctl --vacuum-size=40M",
        "mkdir -p /opt/niteos/data /opt/niteos/app",
        "df -h /",
    ]:
        code, text = run(client, cmd, timeout=60)
        print(cmd, "->", code, text.strip()[:200])

    sftp = client.open_sftp()
    for rel in UPLOAD_DIRS:
        put_dir(sftp, ROOT / rel, f"{REMOTE}/{rel}")
    for rel in UPLOAD_FILES:
        sftp.put(str(ROOT / rel), f"{REMOTE}/{rel}")
    bot_env = (
        f"BOT_TOKEN={env['BOT_TOKEN']}\n"
        f"DADATA_API_KEY={env['DADATA_API_KEY']}\n"
        f"DATA_DIR=/opt/niteos/data\n"
        f"REGION={env.get('REGION', 'Татарстан')}\n"
        f"CITY={env.get('CITY', 'Казань')}\n"
    )
    with sftp.file(f"{REMOTE}/.env", "w") as fh:
        fh.write(bot_env)
    sftp.close()
    print("uploaded")

    install = (
        "set -e; "
        "cd /opt/niteos; "
        "python3 -m venv .venv; "
        ".venv/bin/pip install --upgrade pip; "
        ".venv/bin/pip install -r requirements.txt"
    )
    code, text = run(client, install, timeout=300)
    print("venv", code)
    print(text[-2500:])
    if code != 0:
        client.close()
        raise SystemExit("pip install failed")

    unit = """[Unit]
Description=Niteos hunt Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/niteos
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/niteos/.venv/bin/python -m app.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    sftp = client.open_sftp()
    with sftp.file("/etc/systemd/system/niteos-bot.service", "w") as fh:
        fh.write(unit)
    sftp.close()

    code, text = run(
        client,
        "systemctl daemon-reload && systemctl enable niteos-bot && systemctl restart niteos-bot && sleep 2 && systemctl is-active niteos-bot && journalctl -u niteos-bot -n 30 --no-pager",
        timeout=60,
    )
    print("service", code)
    print(text[-3000:])
    client.close()


if __name__ == "__main__":
    main()
