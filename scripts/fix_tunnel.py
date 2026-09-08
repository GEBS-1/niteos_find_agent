from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

TUNNEL_UNIT = """[Unit]
Description=Cloudflare tunnel for Niteos mini app
After=network-online.target niteos-bot.service
Wants=network-online.target niteos-bot.service

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:8088
Restart=always
RestartSec=5
StandardOutput=append:/var/log/cloudflared-niteos.log
StandardError=append:/var/log/cloudflared-niteos.log

[Install]
WantedBy=multi-user.target
"""


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    sftp = client.open_sftp()
    with sftp.file("/etc/systemd/system/niteos-tunnel.service", "w") as fh:
        fh.write(TUNNEL_UNIT)
    sftp.close()
    code, text = run(
        client,
        ": > /var/log/cloudflared-niteos.log; systemctl daemon-reload; systemctl restart niteos-tunnel; sleep 12; "
        "systemctl is-active niteos-tunnel; tail -n 25 /var/log/cloudflared-niteos.log",
        timeout=40,
    )
    print("restart", code)
    print(out(text)[-2500:])

    code, text = run(
        client,
        "python3 - <<'PY'\n"
        "import re,time,pathlib,urllib.request\n"
        "p=pathlib.Path('/var/log/cloudflared-niteos.log')\n"
        "url=''\n"
        "for i in range(15):\n"
        "    t=p.read_text(encoding='utf-8',errors='replace') if p.exists() else ''\n"
        "    m=re.findall(r'https://[a-z0-9-]+\\.trycloudflare.com', t, re.I)\n"
        "    if m:\n"
        "        url=m[-1]; break\n"
        "    time.sleep(2)\n"
        "print('URL', url or 'NO_URL')\n"
        "if url:\n"
        "    try:\n"
        "        r=urllib.request.urlopen(url, timeout=20)\n"
        "        body=r.read(200).decode('utf-8','replace')\n"
        "        print('PUBLIC', r.status, 'Охота' in body, body[:80])\n"
        "    except Exception as e:\n"
        "        print('PUBLIC_ERR', type(e).__name__, e)\n"
        "PY",
        timeout=60,
    )
    print("probe", text)

    url = ""
    for line in text.splitlines():
        if line.startswith("URL https://"):
            url = line.split(" ", 1)[1].strip()
    if url:
        Path(ROOT / "scripts" / "webapp_url.txt").write_text(url + "\n", encoding="utf-8")
        print("saved", url)
    client.close()


if __name__ == "__main__":
    main()
