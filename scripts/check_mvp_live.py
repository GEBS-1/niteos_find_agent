from sshutil import load_env, run, ssh_connect

c = ssh_connect(load_env())
cmds = [
    "systemctl is-active mvp1-api mvp1-web mvp1-tunnel niteos-bot",
    "systemctl status mvp1-api mvp1-web mvp1-tunnel --no-pager -l | head -60",
    "ss -tlnp | grep -E '8089|3020'",
    "curl -sS -o /dev/null -w 'local_web:%{http_code}\\n' http://127.0.0.1:3020/",
    "curl -sS -o /dev/null -w 'local_api:%{http_code}\\n' http://127.0.0.1:8089/",
    "grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' /opt/mvp_1/cloudflared.log | tail -3",
    "tail -15 /opt/mvp_1/cloudflared.log",
    "df -h /",
    "free -h",
]
for cmd in cmds:
    _, t = run(c, cmd, timeout=40)
    print(f"=== {cmd} ===\n{t}\n")
c.close()
