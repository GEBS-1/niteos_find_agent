from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    for cmd in [
        "df -h /",
        "du -h --max-depth=1 / 2>/dev/null | sort -h | tail -n 15",
        "python3 -m pip --version",
        "python3 -m venv --help >/dev/null && echo venv_ok || echo venv_missing",
        "ls /opt /root 2>/dev/null | head",
    ]:
        code, text = run(client, cmd)
        print("===", cmd, "exit", code)
        print(text[:4000])
    client.close()


if __name__ == "__main__":
    main()
