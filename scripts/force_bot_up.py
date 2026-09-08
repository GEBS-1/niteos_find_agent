from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        ("systemctl kill -s SIGKILL niteos-bot || true; sleep 1; systemctl reset-failed niteos-bot || true", 20),
        ("systemctl start niteos-bot", 20),
        ("sleep 3; systemctl is-active niteos-bot niteos-https-tunnel; systemctl status niteos-bot --no-pager -l | head -25", 25),
        ("journalctl -u niteos-bot -n 30 --no-pager -o cat", 15),
        (
            "ssh -i /root/.ssh/bypass_ed25519 -o BatchMode=yes -o ConnectTimeout=8 root@95.81.112.200 "
            "'systemctl is-active niteos-edge; curl -sS -o /dev/null -w edge=%{http_code}\\\\n --max-time 12 "
            "https://wayne-laws-historic-touring.trycloudflare.com/'",
            30,
        ),
    ]
    for cmd, timeout in cmds:
        print("===", cmd[:100])
        try:
            code, text = run(client, cmd, timeout=timeout)
            print(code, out(text)[-2000:])
        except Exception as exc:
            print("ERR", type(exc).__name__, exc)
    client.close()


if __name__ == "__main__":
    main()
