from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    code, text = run(client, "sed -n '1,160p' /opt/affiliate-factory/server.js", timeout=15)
    (ROOT / "scripts" / "aff_server_head.js").write_text(text, encoding="utf-8")
    print("lines", text.count("\n"), "code", code)
    client.close()


if __name__ == "__main__":
    main()
