from sshutil import load_env, run, ssh_connect

c = ssh_connect(load_env())
cmds = [
    "ps aux | grep -E 'pip|npm|node|uvicorn|next' | grep -v grep",
    "ls -la /opt/mvp_1/.venv/lib/python3.14/site-packages/ 2>/dev/null | tail -5",
    "du -sh /opt/mvp_1/.venv 2>/dev/null",
    "tail -20 /var/log/syslog 2>/dev/null | grep -i oom || dmesg | tail -5",
    "cd /opt/mvp_1 && .venv/bin/pip list 2>/dev/null | tail -15",
]
for cmd in cmds:
    code, text = run(c, cmd, timeout=60)
    print(f"=== {cmd} ===")
    print(text[:4000])
c.close()
