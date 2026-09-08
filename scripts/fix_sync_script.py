from sshutil import load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    for cmd in [
        "sed -i 's/\\r$//' /opt/niteos/scripts/sync_webapp_url.sh",
        "bash /opt/niteos/scripts/sync_webapp_url.sh; echo sync_ok",
        "systemctl list-timers niteos-sync-webapp.timer --no-pager",
        "journalctl -u niteos-bot -n 20 --no-pager -o cat",
    ]:
        code, text = run(client, cmd, timeout=45)
        print("===", cmd[:65])
        print(text.encode("ascii", "replace").decode()[-1200:])
    client.close()


if __name__ == "__main__":
    main()
