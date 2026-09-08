from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes -o ConnectTimeout=10 root@95.81.112.200 'bash -s' <<'EOS'
set -e
curl -sS -o /dev/null -w "cf:%{http_code} t=%{time_total}\n" --max-time 10 https://api.cloudflare.com/client/v4/ || true
curl -sS -o /dev/null -w "google:%{http_code}\n" --max-time 8 https://www.google.com/ || true
mkdir -p /opt/niteos-edge
if [ ! -x /opt/niteos-edge/cloudflared ]; then
  curl -sSL -o /tmp/cloudflared.tgz https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.tgz || \
  curl -sSL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  if [ -f /tmp/cloudflared.tgz ]; then
    tar -xzf /tmp/cloudflared.tgz -C /opt/niteos-edge
    chmod +x /opt/niteos-edge/cloudflared || true
  fi
  if [ -f /tmp/cloudflared ]; then
    mv /tmp/cloudflared /opt/niteos-edge/cloudflared
    chmod +x /opt/niteos-edge/cloudflared
  fi
fi
/opt/niteos-edge/cloudflared --version || ls -la /opt/niteos-edge
df -h / | tail -1
EOS
"""
    code, text = run(client, cmd, timeout=120)
    Path(ROOT / "scripts" / "bypass_cf_install.txt").write_text(text, encoding="utf-8")
    print("code", code)
    print(text[-1500:].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
