from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        "getent hosts vds2946116.my-ihor.ru; dig +short vds2946116.my-ihor.ru A 2>/dev/null || true",
        "curl -sS -o /dev/null -w 'bypass80:%{http_code}\\n' --max-time 5 http://95.81.112.200/ || true",
        "curl -sS -o /dev/null -w 'bypass443:%{http_code}\\n' --max-time 5 https://95.81.112.200/ || true",
        # try pulling cloudflared image size estimate / availability
        "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes -o ConnectTimeout=10 root@95.81.112.200 'docker images; free -m | head -3; df -h / | tail -1'",
    ]
    parts = []
    for cmd in cmds:
        code, text = run(client, cmd, timeout=40)
        parts.append(f"===== {cmd[:90]} -> {code}\n{text}\n")
    Path(ROOT / "scripts" / "bypass_dns.txt").write_text("\n".join(parts), encoding="utf-8")
    print("ok")
    client.close()


if __name__ == "__main__":
    main()
