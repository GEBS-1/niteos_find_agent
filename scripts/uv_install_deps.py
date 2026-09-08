from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        "export PATH=\"$HOME/.local/bin:$PATH\"; cd /opt/niteos; uv venv .venv --python 3.12; UV_NO_CACHE=1 uv pip install -r requirements.txt --python .venv/bin/python",
        "df -h /",
        "ls /opt/niteos/.venv/bin/python",
    ]
    for cmd in cmds:
        code, text = run(client, cmd, timeout=180)
        print("===", cmd[:80], "->", code)
        print(text.encode("ascii", "replace").decode("ascii")[-3000:])
    client.close()


if __name__ == "__main__":
    main()
