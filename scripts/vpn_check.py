from pathlib import Path

from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        "systemctl cat telegram-socks.service",
        "grep -E 'Proxy|PROXY|SOCKS|1080|9050' /etc/systemd/system/prepromo-*.service /etc/systemd/system/telegram-socks.service 2>/dev/null || true",
        "ss -tlnp | grep -E '1080|9050|3010'",
        "systemctl is-active telegram-socks telegram-socks-watch warp-svc tor@default",
        "curl -s -o /dev/null -w 'direct_tg:%{http_code} time:%{time_total}\\n' --max-time 8 https://api.telegram.org || true",
        "curl -s -o /dev/null -w 'socks_tg:%{http_code} time:%{time_total}\\n' --max-time 12 --socks5-hostname 127.0.0.1:1080 https://api.telegram.org || true",
    ]
    chunks = []
    for cmd in cmds:
        code, text = run(client, cmd, timeout=25)
        chunks.append(f"===== {cmd}\\n{text}\\n")
    Path("vpn_check.txt").write_text("\\n".join(chunks), encoding="utf-8")
    print("ok")
    client.close()


if __name__ == "__main__":
    main()
