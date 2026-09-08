from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        "systemctl is-active niteos-tunnel niteos-bot; systemctl status niteos-tunnel --no-pager -l | tail -30",
        "tail -n 40 /var/log/cloudflared-niteos.log",
        "curl -sS -o /dev/null -w 'local:%{http_code}\\n' --max-time 5 http://127.0.0.1:8088/",
        "ss -lntp | grep 8088 || true",
    ]
    for cmd in cmds:
        print("====", cmd[:70])
        code, text = run(client, cmd, timeout=25)
        print(code, out(text)[-2000:])
    client.close()


if __name__ == "__main__":
    main()
