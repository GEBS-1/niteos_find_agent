"""Full server health check for Niteos bot + WebApp HTTPS chain."""
from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    checks = [
        ("services", "systemctl is-active niteos-bot niteos-https-tunnel telegram-socks 2>/dev/null; systemctl is-failed niteos-bot niteos-https-tunnel 2>/dev/null || true"),
        ("listen", "ss -lntp | grep -E '8088|1080' || true"),
        ("env_webapp", "grep -E '^(WEBAPP_URL|WEBAPP_TOKEN|WEBAPP_PORT|TELEGRAM_PROXY|BOT_TOKEN)=' /opt/niteos/.env | sed 's/=.*/=***/'"),
        ("env_full_webapp", "grep ^WEBAPP_URL= /opt/niteos/.env"),
        ("local_app", "curl -sS -o /dev/null -w 'local8088=%{http_code}\\n' --max-time 5 http://127.0.0.1:8088/ || echo local_fail"),
        ("local_meta", "curl -sS -o /dev/null -w 'meta=%{http_code}\\n' --max-time 5 http://127.0.0.1:8088/api/meta || echo meta_fail"),
        ("bot_log", "journalctl -u niteos-bot -n 40 --no-pager -o cat"),
        ("tunnel_log", "journalctl -u niteos-https-tunnel -n 25 --no-pager -o cat 2>/dev/null || echo no_tunnel_unit"),
        ("disk", "df -h / | tail -1"),
        ("bypass_ssh", "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes -o ConnectTimeout=8 root@95.81.112.200 'systemctl is-active niteos-edge 2>/dev/null; ss -lntp | grep 18088; curl -sS -o /dev/null -w edge18088=%{http_code}\\\\n --max-time 5 http://127.0.0.1:18088/' 2>&1 || echo bypass_fail"),
    ]
    for name, cmd in checks:
        print(f"\n=== {name} ===")
        try:
            code, text = run(client, cmd, timeout=45)
            print(code, out(text)[-2500:])
        except Exception as exc:
            print("ERR", exc)

    # test public WEBAPP_URL if set
    code, url_line = run(client, "grep ^WEBAPP_URL= /opt/niteos/.env", timeout=10)
    url = url_line.strip().split("=", 1)[-1].strip() if "=" in url_line else ""
    if url:
        print(f"\n=== public_url {url} ===")
        for cmd in [
            f"curl -sS -o /tmp/niteos_pub.html -w 'pub=%{{http_code}}\\n' --max-time 25 '{url}/'",
            f"curl -sS -o /dev/null -w 'pub_meta=%{{http_code}}\\n' --max-time 15 '{url}/api/meta'",
            "python3 -c \"import os; t=open('/tmp/niteos_pub.html',encoding='utf-8',errors='replace').read() if os.path.exists('/tmp/niteos_pub.html') else ''; print('len',len(t),'hunt',('Охота' in t or 'Niteos' in t)); print(t[:120] if t else 'empty')\"",
        ]:
            code, text = run(client, cmd, timeout=35)
            print(out(text)[-800:])
    else:
        print("\n=== NO WEBAPP_URL ===")

    client.close()


if __name__ == "__main__":
    main()
