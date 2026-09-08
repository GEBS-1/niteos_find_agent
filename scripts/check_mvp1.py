from sshutil import load_env, run, ssh_connect

c = ssh_connect(load_env())
cmds = [
    "ls -lh /tmp/mvp1_deploy.tgz 2>/dev/null || echo NO_TAR",
    "du -sh /opt/mvp_1 2>/dev/null || echo NO_DIR",
    "systemctl is-active mvp1-api mvp1-web mvp1-tunnel 2>/dev/null || true",
    "ss -tlnp | grep -E '8089|3020' || echo NO_PORTS",
    "df -h /",
    "ps aux | grep mvp | grep -v grep || true",
]
for cmd in cmds:
    code, text = run(c, cmd, timeout=30)
    print(f"=== {cmd} ({code}) ===")
    print(text)
c.close()
