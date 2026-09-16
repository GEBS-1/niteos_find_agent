"""Restart deployed Cloudflare tunnel and sync WEBAPP_URL."""
from __future__ import annotations

import re
import time
from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    try:
        commands = [
            "systemctl daemon-reload",
            "systemctl enable niteos-tunnel",
            "systemctl restart niteos-tunnel",
        ]
        for cmd in commands:
            code, text = run(client, cmd, timeout=30)
            print(cmd, "->", code, out(text[-500:]))
            if code != 0:
                raise SystemExit(code)

        url = ""
        for _ in range(30):
            code, text = run(
                client,
                "grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' "
                "/var/log/cloudflared-niteos.log | tail -1",
                timeout=10,
            )
            if code == 0:
                match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
                if match:
                    url = match.group(0)
                    break
            time.sleep(2)
        if not url:
            raise SystemExit("No trycloudflare URL in tunnel log")

        code, text = run(
            client,
            "python3 - <<'PY'\n"
            "from pathlib import Path\n"
            f"url={url!r}\n"
            "p=Path('/opt/niteos/.env')\n"
            "lines=[]\n"
            "if p.exists():\n"
            "    lines=[ln for ln in p.read_text(encoding='utf-8').splitlines() if not ln.startswith('WEBAPP_URL=')]\n"
            "lines.append('WEBAPP_URL='+url)\n"
            "p.write_text('\\n'.join(lines)+'\\n', encoding='utf-8')\n"
            "print('WEBAPP_URL synced')\n"
            "PY\n"
            "systemctl restart niteos-bot\n"
            "sleep 3\n"
            "systemctl is-active niteos-tunnel niteos-bot\n"
            f"curl -sS -o /dev/null -w 'public=%{{http_code}}\\n' --max-time 20 {url}/",
            timeout=60,
        )
        print(out(text[-2000:]))
        if code != 0:
            raise SystemExit(code)
        Path(ROOT / "scripts" / "webapp_url.txt").write_text(url + "\n", encoding="utf-8")
        print("URL", url)
    finally:
        client.close()


if __name__ == "__main__":
    main()
