from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        "rm -rf /tmp/pip-install-* /tmp/pip-build-* /tmp/pip-ephem-* /root/.cache/pip /root/.cargo /opt/niteos/.venv",
        "df -h /",
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "export PATH=\"$HOME/.local/bin:$PATH\"; uv --version",
    ]
    for cmd in cmds:
        code, text = run(client, cmd, timeout=120)
        print("===", cmd[:80], "->", code)
        print(text.encode("ascii", "replace").decode("ascii")[-2000:])
    client.close()


if __name__ == "__main__":
    main()
