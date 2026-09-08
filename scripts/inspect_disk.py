from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    for cmd in [
        "du -sh /var/cache/apt /var/log /var/lib/snapd /snap 2>/dev/null",
        "snap list 2>/dev/null",
        "du -sh /opt/* /root/* 2>/dev/null | sort -h",
        "ls /var/log | head",
        "journalctl --disk-usage 2>/dev/null",
    ]:
        code, text = run(client, cmd)
        print("===", cmd, "exit", code)
        print(text[:5000])
    client.close()


if __name__ == "__main__":
    main()
