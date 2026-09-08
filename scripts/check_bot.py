import time

import httpx

from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    r = httpx.get(f"https://api.telegram.org/bot{env['BOT_TOKEN']}/getMe", timeout=20)
    print("telegram", r.status_code, r.json().get("ok"), r.json().get("result", {}).get("username"))
    time.sleep(4)
    client = ssh_connect(env)
    code, text = run(client, "systemctl is-active niteos-bot; journalctl -u niteos-bot -n 50 --no-pager")
    print(code)
    print(text.encode("ascii", "replace").decode("ascii")[-4000:])
    client.close()


if __name__ == "__main__":
    main()
