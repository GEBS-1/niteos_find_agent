from pathlib import Path

from sshutil import load_env, run, ssh_connect


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    cmds = [
        "grep -iE 'puppeteer|playwright|chromium|chrome' /opt/affiliate-factory/package.json /opt/affiliate-factory/package-lock.json 2>/dev/null | head",
        "pm2 jlist 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin);\\n"
        "print([(x['name'], x['pm2_env'].get('status'), x['pm2_env'].get('restart_time'), x['pm2_env'].get('unstable_restarts')) for x in d])\"",
        "ss -tlnp | grep 8010 || echo '8010 closed'",
        "systemctl is-active snap.chromium.daemon.service; snap services 2>/dev/null | head",
    ]
    # simpler pm2
    cmds = [
        "grep -iE 'puppeteer|playwright|chromium' /opt/affiliate-factory/package.json 2>/dev/null || echo no_browser_dep",
        "ss -tlnp | grep 8010 || echo pers_api_8010_closed",
        "systemctl is-active snap.chromium.daemon.service || true",
        "tail -n 15 /root/.pm2/logs/affiliate-factory-error-0.log 2>/dev/null",
    ]
    chunks = []
    for cmd in cmds:
        code, text = run(client, cmd, timeout=20)
        chunks.append(f"{cmd}\n{text}\n")
    Path("audit3.txt").write_text("\n".join(chunks), encoding="utf-8")
    print("ok")
    client.close()


if __name__ == "__main__":
    main()
