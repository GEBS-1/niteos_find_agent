from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    remote = r"""
ssh -i /root/.ssh/bypass_ed25519 -o StrictHostKeyChecking=accept-new -o ConnectTimeout=12 -o BatchMode=yes root@95.81.112.200 'bash -s' <<'EOS'
set +e
echo HOST=$(hostname)
echo UNAME=$(uname -a)
echo ----ports----
ss -lntp | head -40
echo ----pkgs----
command -v nginx; command -v caddy; command -v cloudflared; command -v docker; command -v certbot; command -v python3
echo ----disk----
df -h / | tail -1
echo ----http----
curl -sS -o /dev/null -w "local80:%{http_code}\n" --max-time 3 http://127.0.0.1/ || true
curl -sS -o /dev/null -w "local443:%{http_code}\n" --max-time 3 https://127.0.0.1/ || true
echo ----sshd----
grep -E '^(GatewayPorts|AllowTcpForwarding|PermitRoot)' /etc/ssh/sshd_config || true
echo ----os----
cat /etc/os-release | head -5
EOS
"""
    code, text = run(client, remote, timeout=40)
    Path(ROOT / "scripts" / "bypass_detail.txt").write_text(text, encoding="utf-8")
    print("code", code, "bytes", len(text))
    client.close()


if __name__ == "__main__":
    main()
