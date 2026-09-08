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

    for cmd, timeout in [
        ("timeout 20 df -h /", 30),
        ("timeout 25 snap list || true", 40),
        ("apt-get clean; journalctl --vacuum-size=40M; timeout 20 df -h /", 60),
    ]:
        code, text = run(client, cmd, timeout=timeout)
        log.append(f"{cmd} -> {code}\n{out(text)[-1200:]}")
        print("===", cmd, "->", code)
        print(out(text)[-800:])

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
    print("uploaded")

    code, text = run(
        client,
        "export PATH=\"$HOME/.local/bin:$PATH\"; cd /opt/niteos; UV_NO_CACHE=1 uv pip install -r requirements.txt --python .venv/bin/python",
        timeout=240,
    )
    log.append(f"pip -> {code}\n{out(text)[-2000:]}")
    print("pip", code, out(text)[-1500:])
    if code != 0:
        Path("fix_result.txt").write_text("\n\n".join(log), encoding="utf-8")
        client.close()
        raise SystemExit("pip failed")

    code, text = run(
        client,
        "systemctl daemon-reload && systemctl enable niteos-bot && systemctl restart telegram-socks && sleep 3 && systemctl restart niteos-bot && sleep 6 && systemctl is-active niteos-bot telegram-socks && journalctl -u niteos-bot -n 25 --no-pager -o cat",
        timeout=90,
    )
    log.append(f"svc -> {code}\n{out(text)}")
    print("svc", code)
    print(out(text)[-2500:])

    token = env["BOT_TOKEN"]
    code, text = run(
        client,
        f"curl -sS --max-time 20 --socks5-hostname 127.0.0.1:1080 https://api.telegram.org/bot{token}/getMe",
        timeout=30,
    )
    log.append(f"getMe -> {code}\n{out(text)}")
    print("getMe", code, out(text))

    Path("fix_result.txt").write_text("\n\n".join(log), encoding="utf-8")
    client.close()
    print("done")


if __name__ == "__main__":
    main()
