from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmds = [
        "grep -RIn \"listen\\|3010\\|express()\\|createServer\" /opt/affiliate-factory --include='*.js' --include='*.mjs' --include='*.cjs' --include='*.ts' -m 30 2>/dev/null | head -40",
        "ls /opt/affiliate-factory | head -30",
        "timeout 20 ssh -o StrictHostKeyChecking=no -o ExitOnForwardFailure=yes -R 80:127.0.0.1:8088 nokey@localhost.run 2>&1 | head -20 || true",
    ]
    for cmd in cmds:
        print("====", cmd[:90])
        try:
            code, text = run(client, cmd, timeout=30)
            print(code, out(text)[-2500:])
        except Exception as exc:
            print("ERR", type(exc).__name__, exc)
    client.close()


if __name__ == "__main__":
    main()
