from sshutil import load_env, run, ssh_connect

c = ssh_connect(load_env())
cmds = [
    "python3 --version",
    "/opt/niteos/.venv/bin/python --version",
    "which python3.11 python3.12 python3.13 2>/dev/null; ls /usr/bin/python3*",
]
for cmd in cmds:
    _, t = run(c, cmd, timeout=20)
    print(cmd, "->", t.strip())
c.close()
