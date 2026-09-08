from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def step(client, cmd: str, timeout: int) -> None:
    print(f"\n===== {cmd[:100]}")
    code, text = run(client, cmd, timeout=timeout)
    print("code", code)
    print(out(text)[-2500:])


def main() -> None:
    client = ssh_connect(load_env())
    step(client, "du -sh /root/.cache /root/.npm /root/.local /var/lib/snapd/cache 2>/dev/null; snap changes | tail -20", 40)
    step(
        client,
        "rm -rf /root/.cache/* /root/.npm/_cacache /tmp/*; mkdir -p /var/cache/apt/archives/partial; df -h /",
        60,
    )
    step(client, "snap abort --all || true; snap changes | tail -15", 40)

    for name in ["chromium", "cups", "gnome-46-2404", "gtk-common-themes", "mesa-2404"]:
        step(client, f"snap remove --purge {name}", 600)

    step(client, "df -h /; echo '---'; snap list; echo '---'; du -sh /snap /var/lib/snapd", 60)
    step(
        client,
        "systemctl is-active niteos-bot telegram-socks; journalctl -u niteos-bot -n 6 --no-pager -o cat",
        20,
    )
    client.close()
    print("done")


if __name__ == "__main__":
    main()
