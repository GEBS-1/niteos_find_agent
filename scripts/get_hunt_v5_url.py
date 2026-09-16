from __future__ import annotations

from sshutil import load_env, run, ssh_connect


CMD = r"""
grep -E '^WEBAPP_URL=' /opt/niteos/.env 2>/dev/null || true
grep -hoE 'https://[a-z0-9-]+\.trycloudflare\.com' \
  /var/log/cloudflared-niteos.log /opt/niteos-edge/cloudflared.log 2>/dev/null | tail -5 || true
systemctl is-active niteos-bot niteos-tunnel niteos-https-tunnel 2>/dev/null || true
"""


def main() -> None:
    client = ssh_connect(load_env())
    code, text = run(client, CMD, timeout=30)
    print(text)
    client.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
