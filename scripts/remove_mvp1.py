"""Remove MVP_1 from VPS completely."""
from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    c = ssh_connect(load_env())
    cmd = """
set -e
systemctl stop mvp1-tunnel mvp1-web mvp1-api 2>/dev/null || true
systemctl disable mvp1-tunnel mvp1-web mvp1-api 2>/dev/null || true
rm -f /etc/systemd/system/mvp1-tunnel.service
rm -f /etc/systemd/system/mvp1-web.service
rm -f /etc/systemd/system/mvp1-api.service
systemctl daemon-reload
systemctl reset-failed mvp1-tunnel mvp1-web mvp1-api 2>/dev/null || true
pkill -f '/opt/mvp_1' 2>/dev/null || true
sleep 1
rm -rf /opt/mvp_1
echo '--- after remove ---'
ls -la /opt/
df -h /
systemctl is-active niteos-bot
ss -tlnp | grep -E '8089|3020' || echo 'mvp ports free'
"""
    code, text = run(c, cmd, timeout=120)
    print(out(text))
    print("exit", code)
    c.close()


if __name__ == "__main__":
    main()
