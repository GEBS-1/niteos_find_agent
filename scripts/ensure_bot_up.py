from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    for cmd, timeout in [
        ("systemctl start niteos-bot; sleep 6; systemctl is-active niteos-bot niteos-https-tunnel", 30),
        ("journalctl -u niteos-bot -n 25 --no-pager -o cat", 15),
        (
            "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes root@95.81.112.200 "
            "'systemctl is-active niteos-edge; ss -lntp | grep 18088'",
            20,
        ),
    ]:
        print("===", cmd[:90])
        code, text = run(client, cmd, timeout=timeout)
        print(code, out(text)[-1800:])
    client.close()


if __name__ == "__main__":
    main()
