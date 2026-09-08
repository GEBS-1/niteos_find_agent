from sshutil import load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    code, text = run(client, "python3 -c \"print(open('/opt/affiliate-factory/ecosystem.config.cjs',encoding='utf-8',errors='replace').read()[:1500])\"", timeout=15)
    (open := __import__("pathlib").Path)(__file__).with_name("aff_eco.txt").write_text(text, encoding="utf-8")
    print("ok", code, len(text))
    client.close()


if __name__ == "__main__":
    main()
