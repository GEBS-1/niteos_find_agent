from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        ("df -h /; df -i /", 30),
        ("timeout 20 snap list; echo SNAP_EXIT:$?; systemctl is-active snapd; journalctl -u snapd -n 15 --no-pager -o cat", 40),
        ("du -xh --max-depth=1 / 2>/dev/null | sort -h | tail -20", 90),
        ("du -xh --max-depth=1 /var /opt /snap /usr /home /root 2>/dev/null | sort -h | tail -40", 90),
        ("ls -lah /snap /var/lib/snapd 2>/dev/null | head -40; du -sh /snap /var/lib/snapd /var/lib/snapd/snaps /var/cache 2>/dev/null", 40),
        ("lsof +L1 2>/dev/null | awk '{print $7,$9}' | sort -n | tail -20", 40),
        ("systemctl is-active niteos-bot telegram-socks; journalctl -u niteos-bot -n 8 --no-pager -o cat", 20),
    ]
    for cmd, timeout in cmds:
        print("\n===== ", cmd[:90])
        try:
            code, text = run(client, cmd, timeout=timeout)
            print("code", code)
            print(out(text)[-3500:])
        except Exception as exc:
            print("ERR", type(exc).__name__, exc)
    client.close()


if __name__ == "__main__":
    main()
