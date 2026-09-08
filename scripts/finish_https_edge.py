import re
from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    env = load_env()
    client = ssh_connect(env)

    for cmd, timeout in [
        ("systemctl daemon-reload && systemctl enable --now niteos-https-tunnel && systemctl restart niteos-https-tunnel && sleep 2 && systemctl is-active niteos-https-tunnel", 40),
        ("systemctl is-active niteos-bot || systemctl restart niteos-bot; systemctl is-active niteos-bot", 25),
        (
            "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes -o ConnectTimeout=10 root@95.81.112.200 "
            "'ss -lntp | grep 18088 || echo NO_18088; systemctl restart niteos-edge; sleep 10; "
            "systemctl is-active niteos-edge; grep -oE \"https://[a-z0-9-]+\\.trycloudflare.com\" /opt/niteos-edge/cloudflared.log | tail -5; "
            "tail -n 25 /opt/niteos-edge/cloudflared.log'",
            50,
        ),
    ]:
        print("===", cmd[:90])
        code, text = run(client, cmd, timeout=timeout)
        print(code, out(text)[-2000:])

    code, text = run(
        client,
        "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 "
        "'for i in $(seq 1 15); do u=$(grep -oE \"https://[a-z0-9-]+\\.trycloudflare.com\" "
        "/opt/niteos-edge/cloudflared.log | tail -1); if [ -n \"$u\" ]; then echo URL:$u; exit 0; fi; "
        "sleep 2; done; echo URL:NO; tail -n 40 /opt/niteos-edge/cloudflared.log'",
        timeout=50,
    )
    print("urlfind", out(text)[-2000:])
    urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text, flags=re.I)
    url = urls[-1].rstrip("/") if urls else ""
    if not url:
        client.close()
        raise SystemExit("no url")

    seturl = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"url={url!r}\n"
        "p=Path('/opt/niteos/.env')\n"
        "lines=[ln for ln in p.read_text(encoding='utf-8').splitlines() if not ln.startswith('WEBAPP_URL=')]\n"
        "lines.append('WEBAPP_URL='+url)\n"
        "p.write_text('\\n'.join(lines)+'\\n', encoding='utf-8')\n"
        "print('set', url)\n"
        "PY"
    )
    code, text = run(client, seturl, timeout=15)
    print(out(text))

    code, text = run(
        client,
        "systemctl restart niteos-bot && sleep 6 && systemctl is-active niteos-bot && "
        "journalctl -u niteos-bot -n 25 --no-pager -o cat",
        timeout=40,
    )
    print(out(text)[-2000:])

    code, text = run(
        client,
        f"curl -sS -o /tmp/n.html -w 'code=%{{http_code}}\\n' --max-time 25 {url}/ && "
        "python3 -c \"t=open('/tmp/n.html',encoding='utf-8',errors='replace').read(); print('title', 'Охота' in t, 'len', len(t)); print(t[:100])\"",
        timeout=40,
    )
    print("public", out(text)[-800:])

    # meta via public
    code, text = run(
        client,
        f"curl -sS --max-time 20 {url}/api/meta | python3 -c \"import sys,json; d=json.load(sys.stdin); print(len(d['okved']), len(d['cities']))\"",
        timeout=35,
    )
    print("meta", out(text))

    token = env["BOT_TOKEN"]
    msg = (
        "Доступ починен.\n\n"
        "Мини-приложение теперь через тот же bypass-прокси, что и Telegram API: "
        "HTTPS-туннель с обходного хоста.\n\n"
        "Нажми /start → «Открыть охоту»."
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
    print("notify", code, text[:250])

    Path(ROOT / "scripts" / "webapp_url.txt").write_text(url + "\n", encoding="utf-8")
    client.close()
    print("DONE", url)


if __name__ == "__main__":
    main()
