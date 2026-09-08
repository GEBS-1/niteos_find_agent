from pathlib import Path

from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        "pm2 list; echo ---; ls /root/.pm2/dump.pm2 2>/dev/null; pm2 prettylist 2>/dev/null | head -c 4000",
        "systemctl is-active prepromo-agent prepromo-bot prepromo-morning-scout pm2-root cloudflared-miniapp telegram-socks warp-svc tor@default postgresql@18-main; echo ---enabled---; systemctl is-enabled prepromo-agent prepromo-bot prepromo-morning-scout pm2-root 2>/dev/null",
        "systemctl status prepromo-morning-scout --no-pager -l | head -n 35",
        "systemctl cat prepromo-agent.service prepromo-bot.service 2>/dev/null | head -n 80",
        "pgrep -a chromium; pgrep -a Xorg; pgrep -a gnome; echo ---cups---; systemctl is-active snap.cups.cupsd",
        "curl -s -o /dev/null -w 'affiliate_3010:%{http_code}\n' --max-time 3 http://127.0.0.1:3010/ || true",
        "ls /opt/pers_agent; systemctl list-units --all | grep -i pers; ls /opt/pers_agent/README.md; head -n 40 /opt/pers_agent/README.md",
        "head -n 30 /opt/affiliate-factory/README.md",
        "head -n 20 /opt/affiliate-factory/HEARTBEAT.md",
        "df -h /; du -sh /snap /var/lib/snapd /usr /var /opt /root 2>/dev/null",
    ]
    chunks = []
    for cmd in cmds:
        code, text = run(client, cmd, timeout=45)
        chunks.append(f"===== {cmd[:100]} -> {code}\n{text}\n")
    Path("audit2.txt").write_text("\n".join(chunks), encoding="utf-8")
    print("wrote audit2.txt")
    client.close()


if __name__ == "__main__":
    main()
