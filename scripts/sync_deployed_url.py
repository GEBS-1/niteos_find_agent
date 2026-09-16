"""Sync the current deployed webapp URL into /opt/niteos/.env."""
from __future__ import annotations

import sys
from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    url = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not url.startswith("https://"):
        raise SystemExit("Usage: python scripts/sync_deployed_url.py https://...")
    client = ssh_connect(load_env())
    try:
        sftp = client.open_sftp()
        try:
            with sftp.file("/opt/niteos/.env", "r") as fh:
                text = fh.read().decode("utf-8", "replace")
            lines = [ln for ln in text.splitlines() if not ln.startswith("WEBAPP_URL=")]
            lines.append("WEBAPP_URL=" + url)
            with sftp.file("/opt/niteos/.env", "w") as fh:
                fh.write(("\n".join(lines) + "\n").encode("utf-8"))
        finally:
            sftp.close()
        print("WEBAPP_URL synced")
        for cmd in [
            "systemctl restart niteos-bot",
            "sleep 2; systemctl is-active niteos-bot niteos-tunnel",
            "curl -sS -o /dev/null -w 'local=%{http_code}\\n' --max-time 8 http://127.0.0.1:8088/",
        ]:
            code, text = run(client, cmd, timeout=30)
            print(cmd, "->", code, out(text))
            if code != 0:
                raise SystemExit(code)
        Path(ROOT / "scripts" / "webapp_url.txt").write_text(url + "\n", encoding="utf-8")
        print("URL", url)
    finally:
        client.close()


if __name__ == "__main__":
    main()
