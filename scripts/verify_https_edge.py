import re
from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    url = Path(ROOT / "scripts" / "webapp_url.txt").read_text(encoding="utf-8").strip()
    if not url:
        # from env on server
        code, text = run(client, "grep ^WEBAPP_URL= /opt/niteos/.env", timeout=10)
        url = text.strip().split("=", 1)[-1].strip()
    print("url", url)

    for cmd, timeout in [
        ("systemctl restart niteos-bot", 30),
        ("sleep 4; systemctl is-active niteos-bot niteos-https-tunnel", 20),
        (
            "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 "
            "'ss -lntp | grep 18088; systemctl is-active niteos-edge; "
            "curl -sS -o /dev/null -w local18088=%{http_code}\\\\n --max-time 5 http://127.0.0.1:18088/'",
            25,
        ),
        (f"curl -sS -o /tmp/n.html -w 'pub=%{{http_code}}\\n' --max-time 25 '{url}/'", 35),
        (
            "python3 -c \"t=open('/tmp/n.html',encoding='utf-8',errors='replace').read(); "
            "print('has_hunt', 'Охота' in t or 'Niteos' in t, 'len', len(t)); print(t[:150])\"",
            15,
        ),
        (
            f"curl -sS --max-time 20 '{url}/api/meta' | python3 -c "
            "\"import sys,json; d=json.load(sys.stdin); print('okved',len(d['okved']),'cities',len(d['cities']))\"",
            30,
        ),
        ("journalctl -u niteos-bot -n 15 --no-pager -o cat", 15),
    ]:
        print("===", cmd[:100])
        try:
            code, text = run(client, cmd, timeout=timeout)
            print(code, out(text)[-1500:])
        except Exception as exc:
            print("ERR", type(exc).__name__, exc)

    token = env["BOT_TOKEN"]
    msg = (
        "Готово: мини-приложение открывается по HTTPS.\n\n"
        "Цепочка как у Telegram API: основная VPS → SSH на bypass → Cloudflare HTTPS.\n\n"
        "Жми /start → «Открыть охоту» (кнопка WebApp)."
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
    print("DONE")


if __name__ == "__main__":
    main()
