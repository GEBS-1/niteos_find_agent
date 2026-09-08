from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        "warp-cli --accept-tos status 2>/dev/null; warp-cli --accept-tos settings 2>/dev/null | head -40",
        "grep -oE 'https://[a-z0-9-]+\\.trycloudflare.com' /var/log/cloudflared-miniapp.log | tail -5",
        "hostname -I; curl -sS --max-time 5 ifconfig.me || true",
        "ls /opt/affiliate-factory | head; grep -RIn 'trycloudflare\\|WEB_APP\\|MINI' /opt/affiliate-factory --include='*.json' --include='*.env' --include='*.js' -m 20 2>/dev/null | head -30",
    ]
    for cmd in cmds:
        print("====", cmd[:80])
        try:
            code, text = run(client, cmd, timeout=25)
            print(code, out(text)[-2000:])
        except Exception as exc:
            print("ERR", exc)
    client.close()


if __name__ == "__main__":
    main()
