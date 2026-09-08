from sshutil import ROOT, load_env, run, ssh_connect

REMOTE = "/opt/niteos"
UNIT = """[Unit]
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
    env = load_env()
    client = ssh_connect(env)
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", f"{REMOTE}/app")
    sftp.put(str(ROOT / "requirements.txt"), f"{REMOTE}/requirements.txt")
    bot_env = (
        f"BOT_TOKEN={env['BOT_TOKEN']}\n"
        f"DADATA_API_KEY={env['DADATA_API_KEY']}\n"
        f"DATA_DIR=/opt/niteos/data\n"
        f"REGION={env.get('REGION', 'Татарстан')}\n"
        f"CITY={env.get('CITY', 'Казань')}\n"
    )
    with sftp.file(f"{REMOTE}/.env", "w") as fh:
        fh.write(bot_env)
    with sftp.file("/etc/systemd/system/niteos-bot.service", "w") as fh:
        fh.write(UNIT)
    sftp.close()

    cmds = [
        "cd /opt/niteos && .venv/bin/python -c 'from app.config import load_settings; load_settings(); print(\"config_ok\")'",
        "systemctl daemon-reload && systemctl enable niteos-bot && systemctl restart niteos-bot && sleep 3 && systemctl is-active niteos-bot",
        "journalctl -u niteos-bot -n 40 --no-pager",
    ]
    for cmd in cmds:
        code, text = run(client, cmd, timeout=60)
        print("===", cmd[:70], "->", code)
        print(text.encode("ascii", "replace").decode("ascii")[-3000:])
    client.close()


if __name__ == "__main__":
    main()
