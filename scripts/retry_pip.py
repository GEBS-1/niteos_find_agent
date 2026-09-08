from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    code, text = run(client, "df -h /; ls -la /opt/niteos; test -x /opt/niteos/.venv/bin/python && echo venv_exists || echo no_venv", timeout=30)
    print(code)
    print(text.encode("ascii", "replace").decode("ascii"))
    code, text = run(
        client,
        "cd /opt/niteos && python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt",
        timeout=300,
    )
    print("install", code)
    print(text.encode("ascii", "replace").decode("ascii")[-3500:])
    client.close()


if __name__ == "__main__":
    main()
