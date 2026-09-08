from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    code, text = run(client, "grep -E 'Registered|trycloudflare|ERR |http2' /var/log/cloudflared-niteos.log | tail -30", timeout=15)
    print(out(text)[-2500:])
    client.close()


if __name__ == "__main__":
    main()
