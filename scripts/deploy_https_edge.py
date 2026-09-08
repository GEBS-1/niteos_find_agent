from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

REVERSE_UNIT = """[Unit]
Description=Niteos reverse tunnel to bypass host for HTTPS edge
After=network-online.target niteos-bot.service
Wants=network-online.target niteos-bot.service
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStartPre=-/bin/bash -c 'ss -lntp | grep -q "127.0.0.1:18088" && true'
ExecStart=/usr/bin/ssh -i /root/.ssh/bypass_ed25519 -p 22 \\
  -o StrictHostKeyChecking=accept-new \\
  -o UserKnownHostsFile=/root/.ssh/known_hosts \\
  -o ServerAliveInterval=15 \\
  -o ServerAliveCountMax=3 \\
  -o TCPKeepAlive=yes \\
  -o ExitOnForwardFailure=yes \\
  -o ConnectTimeout=10 \\
  -N -R 127.0.0.1:18088:127.0.0.1:8088 root@95.81.112.200

[Install]
WantedBy=multi-user.target
"""

EDGE_UNIT = """[Unit]
Description=Niteos Cloudflare edge on bypass host
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/niteos-edge
ExecStart=/opt/niteos-edge/cloudflared tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:18088
Restart=always
RestartSec=5
StandardOutput=append:/opt/niteos-edge/cloudflared.log
StandardError=append:/opt/niteos-edge/cloudflared.log

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

    # 1) upload app/web
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    with sftp.file("/etc/systemd/system/niteos-https-tunnel.service", "w") as fh:
        fh.write(REVERSE_UNIT)
    sftp.close()

    # 2) install cloudflared binary on bypass + edge unit
    install = r"""
ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes -o ConnectTimeout=12 root@95.81.112.200 'bash -s' <<'EOS'
set -e
mkdir -p /opt/niteos-edge
cd /opt/niteos-edge
if [ ! -x ./cloudflared ]; then
  curl -fsSL -o cloudflared https://github.com/cloudflare/cloudflared/releases/download/2025.8.1/cloudflared-linux-amd64
  chmod +x cloudflared
fi
./cloudflared --version
cat > /etc/systemd/system/niteos-edge.service <<'UNIT'
""" + EDGE_UNIT + r"""
UNIT
: > /opt/niteos-edge/cloudflared.log
systemctl daemon-reload
systemctl enable niteos-edge
echo INSTALLED
EOS
"""
    code, text = run(client, install, timeout=120)
    print("install", code)
    print(out(text)[-1200:])
    if code != 0:
        # try alternate release URL
        alt = r"""
ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 'bash -s' <<'EOS'
set -e
mkdir -p /opt/niteos-edge
cd /opt/niteos-edge
curl -fsSL -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared
./cloudflared --version
EOS
"""
        code, text = run(client, alt, timeout=120)
        print("alt", code, out(text)[-800:])
        if code != 0:
            raise SystemExit("cloudflared install failed")

    # rewrite edge unit if install path skipped it
    write_unit = r"""
ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 'bash -s' <<'EOS'
cat > /etc/systemd/system/niteos-edge.service <<'UNIT'
""" + EDGE_UNIT + r"""
UNIT
systemctl daemon-reload
systemctl enable niteos-edge
EOS
"""
    code, text = run(client, write_unit, timeout=30)
    print("unit", code, out(text)[-400:])

    # 3) start reverse tunnel then edge
    code, text = run(
        client,
        "systemctl daemon-reload; systemctl enable niteos-https-tunnel; "
        "systemctl restart niteos-bot; sleep 2; "
        "systemctl restart niteos-https-tunnel; sleep 3; "
        "systemctl is-active niteos-bot niteos-https-tunnel; "
        "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 "
        "'ss -lntp | grep 18088 || true; systemctl restart niteos-edge; sleep 8; "
        "systemctl is-active niteos-edge; grep -oE \"https://[a-z0-9-]+\\.trycloudflare.com\" /opt/niteos-edge/cloudflared.log | tail -3; "
        "tail -n 20 /opt/niteos-edge/cloudflared.log'",
        timeout=60,
    )
    print("start", code)
    print(out(text)[-2500:])

    # extract URL
    import re

    urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text, flags=re.I)
    url = urls[-1].rstrip("/") if urls else ""
    print("URL", url)
    if not url:
        # wait more
        code, text = run(
            client,
            "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 "
            "'for i in 1 2 3 4 5 6 7 8 9 10; do "
            "u=$(grep -oE \"https://[a-z0-9-]+\\.trycloudflare.com\" /opt/niteos-edge/cloudflared.log | tail -1); "
            "if [ -n \"$u\" ]; then echo $u; exit 0; fi; sleep 2; done; "
            "echo NO_URL; tail -n 30 /opt/niteos-edge/cloudflared.log'",
            timeout=40,
        )
        print("wait", out(text)[-1500:])
        urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text, flags=re.I)
        url = urls[-1].rstrip("/") if urls else ""

    if not url:
        raise SystemExit("no public url")

    # 4) set WEBAPP_URL and restart bot to publish menu
    seturl = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"url={url!r}\n"
        "p=Path('/opt/niteos/.env')\n"
        "lines=[ln for ln in p.read_text(encoding='utf-8').splitlines() "
        "if not ln.startswith('WEBAPP_URL=')]\n"
        "lines.append('WEBAPP_URL='+url)\n"
        "if not any(ln.startswith('WEBAPP_TOKEN=') for ln in lines):\n"
        "  import secrets; lines.append('WEBAPP_TOKEN='+secrets.token_hex(16))\n"
        "p.write_text('\\n'.join(lines)+'\\n', encoding='utf-8')\n"
        "print('url_set')\n"
        "tok=[ln.split('=',1)[1] for ln in lines if ln.startswith('WEBAPP_TOKEN=')][0]\n"
        "print('TOKEN_LEN', len(tok))\n"
        "PY"
    )
    code, text = run(client, seturl, timeout=15)
    print("env", out(text))

    code, text = run(
        client,
        "systemctl restart niteos-bot; sleep 5; systemctl is-active niteos-bot; "
        "journalctl -u niteos-bot -n 20 --no-pager -o cat",
        timeout=30,
    )
    print("bot", out(text)[-1800:])

    # 5) probe public URL from bypass and from VPS
    probe = (
        f"curl -sS -o /tmp/niteos_edge.html -w 'from_vps:%{{http_code}}\\n' --max-time 20 {url}/; "
        f"head -c 120 /tmp/niteos_edge.html; echo; "
        "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 "
        f"'curl -sS -o /tmp/n.html -w from_edge:%{{http_code}}\\\\n --max-time 15 {url}/; "
        "head -c 100 /tmp/n.html; echo; "
        "curl -sS -o /dev/null -w local_tunnel:%{http_code}\\\\n --max-time 5 http://127.0.0.1:18088/'"
    )
    code, text = run(client, probe, timeout=50)
    print("probe", out(text)[-1500:])

    # 6) notify user
    token = env["BOT_TOKEN"]
    msg = (
        "Починил доступ к мини-приложению.\n\n"
        "Раньше кнопка вела на HTTP/IP или мёртвый Cloudflare с основной VPS — "
        "Telegram/браузер и писали про прокси/DNS.\n\n"
        "Сейчас как у Telegram-бота: через bypass-хост (тот же SSH-прокси) "
        "поднят HTTPS-туннель.\n\n"
        "Жми /start → «Открыть охоту». Там город/Россия, ОКВЭД, количество — "
        "агенты отрабатывают сами."
    )
    sftp = client.open_sftp()
    with sftp.file("/tmp/niteos_tg.txt", "w") as fh:
        fh.write(msg)
    sftp.close()
    send = (
        "python3 - <<'PY'\n"
        "import urllib.parse\n"
        f"token={token!r}\n"
        "text=open('/tmp/niteos_tg.txt',encoding='utf-8').read()\n"
        "open('/tmp/niteos_post.txt','w',encoding='utf-8').write("
        "urllib.parse.urlencode({'chat_id':'388963917','text':text}))\n"
        "PY\n"
        f"curl -sS --max-time 20 --socks5-hostname 127.0.0.1:1080 "
        f"-X POST --data-binary @/tmp/niteos_post.txt "
        f"-H 'Content-Type: application/x-www-form-urlencoded' "
        f"https://api.telegram.org/bot{token}/sendMessage"
    )
    code, text = run(client, send, timeout=30)
    print("notify", code, text[:220])

    Path(ROOT / "scripts" / "webapp_url.txt").write_text(url + "\n", encoding="utf-8")
    client.close()
    print("DONE", url)


if __name__ == "__main__":
    main()
