from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        "systemctl cat prepromo-tunnel.service",
        "ssh -i /root/.ssh/bypass_ed25519 -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o BatchMode=yes root@95.81.112.200 'echo HOST=$(hostname); echo IP=$(hostname -I); ss -lntp | grep -E \":80|:443|:808|:8443|:18088\" || true; command -v nginx; command -v caddy; command -v certbot; ls /etc/nginx/sites-enabled /etc/caddy 2>/dev/null; ufw status | head; grep GatewayPorts /etc/ssh/sshd_config | head'",
        "curl -sS -o /dev/null -w 'pub3010:%{http_code}\\n' --max-time 8 http://127.0.0.1:3010/niteos/ | head",
        "python3 -c \"from pathlib import Path; t=Path('/opt/affiliate-factory/server.js').read_text(); i=t.find('NITEOS_PROXY'); print(t[i-80:i+900])\"",
    ]
    parts = []
    for cmd in cmds:
        try:
            code, text = run(client, cmd, timeout=25)
        except Exception as exc:
            text = f"ERR {type(exc).__name__} {exc}"
            code = -1
        parts.append(f"===== {cmd[:100]} -> {code}\n{text}\n")
    Path(ROOT / "scripts" / "bypass_host.txt").write_text("\n".join(parts), encoding="utf-8")
    print("ok")
    client.close()


if __name__ == "__main__":
    main()
