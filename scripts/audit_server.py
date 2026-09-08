from pathlib import Path

from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        "hostname; uptime; df -h /; free -h",
        "systemctl list-units --type=service --state=running --no-pager --plain",
        "systemctl list-units --type=service --state=failed --no-pager --plain",
        "ps aux --sort=-rss | head -n 25",
        "ss -tulpn",
        "ls -la /opt; du -sh /opt/* 2>/dev/null; ls -la /root",
        "systemctl is-active niteos-bot; systemctl is-enabled niteos-bot; journalctl -u niteos-bot -n 25 --no-pager",
        "ls /etc/systemd/system/*.service; ls /etc/systemd/system/multi-user.target.wants/",
        "snap list",
        "crontab -l; ls /etc/cron.d",
        "for d in /opt/affiliate-factory /opt/pers_agent /opt/prepromo /opt/niteos; do echo ==== $d; ls -la $d 2>/dev/null | head; done",
        "systemctl list-unit-files --type=service --no-pager | grep -Ei 'niteos|prepromo|affiliate|pers|agent|bot|docker|nginx|caddy|node|python'",
    ]
    chunks: list[str] = []
    for cmd in cmds:
        code, text = run(client, cmd, timeout=60)
        chunks.append(f"===== {cmd} -> {code}\n{text}\n")
    client.close()
    Path("audit_out.txt").write_text("\n".join(chunks), encoding="utf-8")
    print("wrote audit_out.txt")


if __name__ == "__main__":
    main()
