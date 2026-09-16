from __future__ import annotations

from sshutil import load_env, run, ssh_connect


REMOTE_SCRIPT = r"""
import asyncio
import json
import sys
sys.path.insert(0, "/opt/niteos")
from app.providers.known_public_sources import known_public_object_candidates
from app.providers.free_maps import FreeMapsObjectProvider


async def main():
    known = known_public_object_candidates("Казань", "складской комплекс", 2)
    maps = await FreeMapsObjectProvider().search("Казань", "складской комплекс", 3)
    print(json.dumps({
        "known": [(r.name, r.source_provider, r.source_url) for r in known],
        "maps": [(r.name, r.source_provider, r.source_url) for r in maps],
    }, ensure_ascii=False, indent=2))


asyncio.run(main())
"""


def main() -> None:
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    path = "/tmp/remote_check_known_source.py"
    with sftp.file(path, "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    code, text = run(client, f"cd /opt/niteos && .venv/bin/python {path}", timeout=90)
    print(text.encode("cp1251", "replace").decode("cp1251", "replace"))
    client.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
