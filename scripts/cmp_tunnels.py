from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        "grep -E 'trycloudflare|Registered|ERR ' /var/log/cloudflared-miniapp.log | tail -15",
        "grep -E 'Registered|ERR |trycloudflare' /var/log/cloudflared-niteos.log | tail -15",
        "systemctl is-active niteos-tunnel cloudflared-miniapp",
        "curl -sS -o /dev/null -w 'local_root:%{http_code} len=%{size_download}\\n' --max-time 5 http://127.0.0.1:8088/",
        "curl -sS --max-time 8 http://127.0.0.1:8088/ | head -c 120",
    ]
    for cmd in cmds:
        print("====", cmd[:75])
        code, text = run(client, cmd, timeout=20)
        print(code, out(text)[-1500:])
    client.close()


if __name__ == "__main__":
    main()
