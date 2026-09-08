from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

REMOTE = "/opt/niteos"
BOT_UNIT = """[Unit]
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
TUNNEL_UNIT = """[Unit]
Description=Cloudflare tunnel for Niteos mini app
After=network-online.target niteos-bot.service
Wants=network-online.target niteos-bot.service

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8088
Restart=always
RestartSec=5
StandardOutput=append:/var/log/cloudflared-niteos.log
StandardError=append:/var/log/cloudflared-niteos.log

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
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", f"{REMOTE}/app")
    put_dir(sftp, ROOT / "web", f"{REMOTE}/web")
    with sftp.file("/etc/systemd/system/niteos-bot.service", "w") as fh:
        fh.write(BOT_UNIT)
    with sftp.file("/etc/systemd/system/niteos-tunnel.service", "w") as fh:
        fh.write(TUNNEL_UNIT)
    sftp.close()

    code, text = run(
        client,
        "grep -q '^WEBAPP_PORT=' /opt/niteos/.env || echo WEBAPP_PORT=8088 >> /opt/niteos/.env; "
        "touch /var/log/cloudflared-niteos.log; "
        "systemctl daemon-reload; "
        "systemctl enable niteos-bot niteos-tunnel; "
        "systemctl restart niteos-bot; "
        "sleep 3; "
        "systemctl restart niteos-tunnel; "
        "sleep 8; "
        "systemctl is-active niteos-bot niteos-tunnel; "
        "ss -lntp | grep 8088 || true",
        timeout=40,
    )
    print("svc", code, out(text)[-1500:])

    code, text = run(
        client,
        "python3 - <<'PY'\n"
        "import re,time,pathlib\n"
        "p=pathlib.Path('/var/log/cloudflared-niteos.log')\n"
        "url=''\n"
        "for i in range(20):\n"
        "    t=p.read_text(encoding='utf-8',errors='replace') if p.exists() else ''\n"
        "    m=re.findall(r'https://[a-z0-9-]+\\.trycloudflare.com', t, re.I)\n"
        "    if m:\n"
        "        url=m[-1]; break\n"
        "    time.sleep(2)\n"
        "print(url or 'NO_URL')\n"
        "PY",
        timeout=50,
    )
    print("url", code, text.strip())
    url = text.strip().splitlines()[-1].strip() if text.strip() else ""

    code, text = run(
        client,
        "curl -sS --max-time 8 http://127.0.0.1:8088/api/meta | python3 -c "
        "\"import sys,json; d=json.load(sys.stdin); print('okved',len(d['okved']),'cities',len(d['cities']))\"",
        timeout=20,
    )
    print("meta", code, out(text))

    hunt = r"""curl -sS --max-time 8 -H 'Content-Type: application/json' -d '{"phrase":"склад","okved":["52.10"],"city":"","count":1}' http://127.0.0.1:8088/api/hunt"""
    code, text = run(client, hunt, timeout=20)
    print("post", code, text)
    hunt_id = ""
    try:
        import json
        hunt_id = str(json.loads(text).get("id") or "")
    except Exception as exc:
        print("post parse", exc)

    if hunt_id:
        poll = (
            "python3 - <<'PY'\n"
            "import json,time,urllib.request\n"
            f"hid={hunt_id!r}\n"
            "data={}\n"
            "for i in range(40):\n"
            "    data=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/hunt/'+hid, timeout=8))\n"
            "    print(data.get('status'), (data.get('progress') or '')[:80])\n"
            "    if data.get('status') in ('done','error'):\n"
            "        break\n"
            "    time.sleep(1)\n"
            "open('/tmp/niteos_web_hunt.json','w',encoding='utf-8').write(json.dumps(data,ensure_ascii=False,indent=2))\n"
            "print('COMPANIES', len(data.get('companies') or []))\n"
            "PY"
        )
        code, text = run(client, poll, timeout=90)
        print("poll", code)
        print(out(text)[-2000:])
        code, raw = run(client, "cat /tmp/niteos_web_hunt.json", timeout=15)
        Path(ROOT / "scripts" / "web_hunt.json").write_text(raw, encoding="utf-8")

    code, text = run(client, "journalctl -u niteos-bot -n 25 --no-pager -o cat", timeout=15)
    print("botlog", out(text)[-1800:])

    if url.startswith("https://"):
        token = env["BOT_TOKEN"]
        msg = (
            "Готово мини-приложение охоты.\n\n"
            "В боте нажми /start → «Открыть охоту», либо кнопку «Охота» слева внизу.\n"
            "Там: вся Россия или город, ОКВЭД из списка (~200) или свой код, сколько компаний.\n"
            "Агенты дальше работают сами и показывают список."
        )
        sftp = client.open_sftp()
        with sftp.file("/tmp/niteos_tg.txt", "w") as fh:
            fh.write(msg)
        sftp.close()
        send = (
            f"python3 - <<'PY'\n"
            "import urllib.parse\n"
            f"token={token!r}\n"
            "text=open('/tmp/niteos_tg.txt',encoding='utf-8').read()\n"
            "open('/tmp/niteos_post.txt','w',encoding='utf-8').write("
            "urllib.parse.urlencode({'chat_id': '388963917', 'text': text}))\n"
            "PY\n"
            f"curl -sS --max-time 20 --socks5-hostname 127.0.0.1:1080 "
            f"-X POST --data-binary @/tmp/niteos_post.txt "
            f"-H 'Content-Type: application/x-www-form-urlencoded' "
            f"https://api.telegram.org/bot{token}/sendMessage"
        )
        code, text = run(client, send, timeout=30)
        print("notify", code, text[:250])
        Path(ROOT / "scripts" / "webapp_url.txt").write_text(url + "\n", encoding="utf-8")

    client.close()
    print("done", url)


if __name__ == "__main__":
    main()
