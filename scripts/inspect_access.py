from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        "systemctl cat telegram-socks.service",
        "ls /etc/systemd/system/*tunnel* /etc/systemd/system/*socks* /etc/systemd/system/*cloudflare* 2>/dev/null",
        "systemctl cat cloudflared-miniapp.service",
        "systemctl cat prepromo-tunnel.service 2>/dev/null | head -40",
        "grep -n NITEOS_PROXY /opt/affiliate-factory/server.js | head",
        "systemctl is-active niteos-bot niteos-tunnel cloudflared-miniapp telegram-socks affiliate-factory 2>/dev/null; pm2 jlist | python3 -c \"import sys,json; d=json.load(sys.stdin); print([(x.get('name'), x.get('pm2_env',{}).get('status')) for x in d])\"",
        "curl -sS -o /dev/null -w 'n8088:%{http_code}\\n' --max-time 5 http://127.0.0.1:8088/; curl -sS -o /dev/null -w 'n3010:%{http_code}\\n' --max-time 5 http://127.0.0.1:3010/; curl -sS -o /dev/null -w 'niteos_path:%{http_code}\\n' --max-time 5 http://127.0.0.1:3010/niteos/",
        "grep -oE 'https://[a-z0-9-]+\\.trycloudflare.com' /var/log/cloudflared-miniapp.log | tail -3",
        "grep WEBAPP /opt/niteos/.env | sed 's/=.*/=***/'",
        "journalctl -u niteos-bot -n 15 --no-pager -o cat",
        "tail -n 8 /var/log/cloudflared-miniapp.log",
    ]
    parts = []
    for cmd in cmds:
        try:
            code, text = run(client, cmd, timeout=25)
        except Exception as exc:
            text = f"ERR {type(exc).__name__} {exc}"
            code = -1
        parts.append(f"===== {cmd[:90]} -> {code}\n{text}\n")
    Path(ROOT / "scripts" / "fix_access.txt").write_text("\n".join(parts), encoding="utf-8")
    print("wrote", len(parts))
    client.close()


if __name__ == "__main__":
    main()
