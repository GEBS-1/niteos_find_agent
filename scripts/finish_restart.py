import re
from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    code, text = run(client, "grep ^WEBAPP_URL= /opt/niteos/.env", timeout=10)
    url = text.strip().split("=", 1)[-1].strip()
    print("WEBAPP_URL", url)

    run(client, "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; systemctl reset-failed niteos-bot || true", timeout=20)
    code, text = run(client, "systemctl start niteos-bot; sleep 4; systemctl is-active niteos-bot", timeout=60)
    print("bot", code, out(text))

    if url:
        for cmd in [
            f"curl -sS -o /tmp/n.html -w 'pub=%{{http_code}}\\n' --max-time 25 '{url}/'",
            f"curl -sS -o /dev/null -w 'meta=%{{http_code}}\\n' --max-time 15 '{url}/api/meta'",
            "python3 -c \"t=open('/tmp/n.html',encoding='utf-8',errors='replace').read(); print('ok',('Охота' in t or 'Niteos' in t), 'len', len(t))\"",
            "journalctl -u niteos-bot -n 12 --no-pager -o cat",
        ]:
            code, text = run(client, cmd, timeout=40)
            print(out(text)[-1200:])

    Path(ROOT / "scripts" / "webapp_url.txt").write_text(url + "\n", encoding="utf-8")
    client.close()
    print("DONE", url)


if __name__ == "__main__":
    main()
