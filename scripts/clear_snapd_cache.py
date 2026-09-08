from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        ("du -sh /var/lib/snapd/cache /var/lib/snapd/snaps /snap; ls /var/lib/snapd/snaps", 30),
        ("rm -rf /var/lib/snapd/cache/*; snap remove --purge core22 || true; df -h /; snap list; du -sh /snap /var/lib/snapd /var/lib/snapd/cache", 180),
        ("systemctl is-active niteos-bot telegram-socks; ss -lntp | grep 1080 || true; journalctl -u niteos-bot -n 12 --no-pager -o cat", 20),
        (
            f"curl -sS --max-time 20 --socks5-hostname 127.0.0.1:1080 https://api.telegram.org/bot{env['BOT_TOKEN']}/getMe",
            30,
        ),
        (
            "curl -sS -o /dev/null -w 'direct_telegram=%{http_code} time=%{time_total}\\n' --max-time 8 https://api.telegram.org/ || echo direct_telegram=blocked",
            15,
        ),
    ]
    for cmd, timeout in cmds:
        print("\n=====")
        try:
            code, text = run(client, cmd, timeout=timeout)
            print("code", code)
            print(out(text)[-2000:])
        except Exception as exc:
            print("ERR", type(exc).__name__, exc)
    client.close()


if __name__ == "__main__":
    main()
