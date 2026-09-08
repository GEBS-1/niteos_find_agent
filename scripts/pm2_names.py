from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    code, text = run(client, "pm2 jlist | python3 -c \"import sys,json; d=json.load(sys.stdin); print('\\n'.join(x.get('name','') for x in d))\"", timeout=15)
    print(out(text))
    client.close()


if __name__ == "__main__":
    main()
