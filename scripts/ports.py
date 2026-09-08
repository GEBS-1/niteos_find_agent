from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        "ss -lntp | grep -E ':80|:443|:8088|:3010'",
        "iptables -L INPUT -n | head -25; ufw status 2>/dev/null | head",
        "command -v caddy; ls /usr/local/bin/caddy /usr/bin/caddy 2>/dev/null",
        "curl -sS --max-time 8 http://127.0.0.1:3010/ | head -c 80",
    ]
    for cmd in cmds:
        print("====", cmd[:70])
        code, text = run(client, cmd, timeout=20)
        print(code, out(text)[-1500:])
    client.close()


if __name__ == "__main__":
    main()
