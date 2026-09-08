from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

URL = "https://wayne-laws-historic-touring.trycloudflare.com"


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    env = load_env()
    client = ssh_connect(env)

    seturl = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"url={URL!r}\n"
        "p=Path('/opt/niteos/.env')\n"
        "lines=[ln for ln in p.read_text(encoding='utf-8').splitlines() if ln and not ln.startswith('WEBAPP_URL=')]\n"
        "lines.append('WEBAPP_URL='+url)\n"
        "p.write_text('\\n'.join(lines)+'\\n', encoding='utf-8')\n"
        "print(p.read_text())\n"
        "PY"
    )
    code, text = run(client, seturl, timeout=15)
    # scrub token from print
    safe = "\n".join(
        (ln.split("=", 1)[0] + "=***") if ("TOKEN" in ln or "PASSWORD" in ln or "KEY" in ln or "BOT_TOKEN" in ln) else ln
        for ln in text.splitlines()
    )
    print("env", out(safe))

    for cmd, timeout in [
        (
            "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 "
            f"'curl -sS -o /tmp/n.html -w edge=%{{http_code}}\\\\n --max-time 20 {URL}/; "
            "python3 -c \"t=open(\\\"/tmp/n.html\\\",encoding=\\\"utf-8\\\",errors=\\\"replace\\\").read(); print(len(t), t[15:60])\"; "
            f"curl -sS --max-time 15 {URL}/api/meta | python3 -c \"import sys,json; d=json.load(sys.stdin); print(len(d[\\\"okved\\\"]), len(d[\\\"cities\\\"]))\"'",
            45,
        ),
        (f"curl -sS -o /tmp/n2.html -w vps=%{{http_code}}\\n --max-time 25 {URL}/; wc -c /tmp/n2.html", 35),
        ("systemctl restart niteos-bot", 25),
        ("sleep 5; systemctl is-active niteos-bot; journalctl -u niteos-bot -n 20 --no-pager -o cat", 25),
    ]:
        print("===", cmd[:100])
        try:
            code, text = run(client, cmd, timeout=timeout)
            print(code, out(text)[-1800:])
        except Exception as exc:
            print("ERR", type(exc).__name__, exc)

    token = env["BOT_TOKEN"]
    msg = (
        "Мини-приложение снова на HTTPS через bypass (как Telegram).\n\n"
        "Жми /start → кнопку «Открыть охоту». "
        "Если старое меню — именно /start заново."
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

    Path(ROOT / "scripts" / "webapp_url.txt").write_text(URL + "\n", encoding="utf-8")
    client.close()
    print("DONE", URL)


if __name__ == "__main__":
    main()
