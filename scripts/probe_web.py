from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        "systemctl cat cloudflared-miniapp.service | head -40",
        "ls -la /etc/cloudflared /root/.cloudflared 2>/dev/null; cloudflared --version 2>/dev/null | head -2",
        "ss -lntp | grep -E '8088|8090|8787|80 |443' || true",
        "df -h / | tail -1",
        "systemctl is-active niteos-bot cloudflared-miniapp",
    ]
    for cmd in cmds:
        print("\n====", cmd[:80])
        code, text = run(client, cmd, timeout=20)
        print(code, out(text)[-2000:])
    client.close()


if __name__ == "__main__":
    main()
