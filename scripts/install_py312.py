from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        "journalctl --vacuum-size=20M; rm -rf /var/cache/apt/archives/*; truncate -s 0 /var/log/syslog /var/log/auth.log /var/log/kern.log 2>/dev/null; find /var/log -name '*.gz' -delete; find /var/log -name '*.1' -delete; rm -f /root/prepromo-sync.tar.gz; df -h /",
        "export PATH=\"$HOME/.local/bin:$PATH\"; uv python install 3.12",
        "df -h /",
        "export PATH=\"$HOME/.local/bin:$PATH\"; uv python list",
    ]
    for cmd in cmds:
        code, text = run(client, cmd, timeout=180)
        print("===", cmd[:70], "->", code)
        print(text.encode("ascii", "replace").decode("ascii")[-2500:])
    client.close()


if __name__ == "__main__":
    main()
