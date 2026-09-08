from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

REMOTE = "/opt/niteos"
UNIT = """[Unit]
Description=Niteos hunt Telegram bot
After=network-online.target telegram-socks.service
Wants=network-online.target telegram-socks.service

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
    client = ssh_connect(env)
    log: list[str] = []

    snaps = [
        "chromium",
        "cups",
        "gnome-46-2404",
        "gtk-common-themes",
        "mesa-2404",
    ]
    for name in snaps:
        cmd = f"snap remove {name}"
        code, text = run(client, cmd, timeout=300)
        log.append(f"{cmd} -> {code}\n{out(text)[-800:]}")
        print(cmd, code)

    code, text = run(client, "df -h /; snap list", timeout=60)
    log.append(out(text))
    print("disk after snaps", out(text)[:500])

    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", f"{REMOTE}/app")
    sftp.put(str(ROOT / "requirements.txt"), f"{REMOTE}/requirements.txt")
    bot_env = (
        f"BOT_TOKEN={env['BOT_TOKEN']}\n"
        f"DADATA_API_KEY={env['DADATA_API_KEY']}\n"
        f"TELEGRAM_PROXY=socks5://127.0.0.1:1080\n"
        f"DATA_DIR=/opt/niteos/data\n"
        f"REGION={env.get('REGION', 'Татарстан')}\n"
        f"CITY={env.get('CITY', 'Казань')}\n"
    )
    with sftp.file(f"{REMOTE}/.env", "w") as fh:
        fh.write(bot_env)
    with sftp.file("/etc/systemd/system/niteos-bot.service", "w") as fh:
        fh.write(UNIT)
    sftp.close()

    code, text = run(
        client,
        "export PATH=\"$HOME/.local/bin:$PATH\"; cd /opt/niteos; UV_NO_CACHE=1 uv pip install -r requirements.txt --python .venv/bin/python",
        timeout=180,
    )
    log.append(f"pip -> {code}\n{out(text)[-1500:]}")
    print("pip", code)

    code, text = run(
        client,
        "systemctl daemon-reload && systemctl restart telegram-socks && sleep 2 && systemctl restart niteos-bot && sleep 4 && systemctl is-active niteos-bot telegram-socks && journalctl -u niteos-bot -n 20 --no-pager",
        timeout=60,
    )
    log.append(f"svc -> {code}\n{out(text)}")
    print("svc", code, out(text)[-1500:])

    token = env["BOT_TOKEN"]
    code, text = run(
        client,
        f"curl -s --max-time 15 --socks5-hostname 127.0.0.1:1080 https://api.telegram.org/bot{token}/getMe",
        timeout=25,
    )
    # don't write full token responses with secrets to disk if possible - getMe is public-ish username
    log.append(f"getMe -> {code}\n{out(text)}")
    print("getMe", code, out(text))

    Path("fix_result.txt").write_text("\n\n".join(log), encoding="utf-8")
    client.close()
    print("done")


if __name__ == "__main__":
    main()
