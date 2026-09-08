from sshutil import load_env, run, ssh_connect

c = ssh_connect(load_env())
cmds = [
    "df -h /",
    "du -sh /opt/* /root/.npm /root/.cache /tmp /var/cache/apt 2>/dev/null | sort -hr | head -20",
    "du -sh /opt/mvp_1/* 2>/dev/null | sort -hr | head -15",
]
for cmd in cmds:
    _, t = run(c, cmd, timeout=60)
    print("===", cmd, "===\n", t)
c.close()
