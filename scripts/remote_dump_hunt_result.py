from __future__ import annotations

import sys

from sshutil import load_env, run, ssh_connect


def main() -> None:
    hunt_id = sys.argv[1] if len(sys.argv) > 1 else "20"
    script = f"""
import json
import urllib.request
rows = json.loads(urllib.request.urlopen('http://127.0.0.1:8088/api/hunts/{hunt_id}/results').read().decode('utf-8'))
for r in rows:
    print(json.dumps({{
        'object': r.get('object'),
        'company': r.get('company'),
        'people_candidates': r.get('people_candidates'),
        'people': r.get('people'),
        'contact_audit': r.get('contact_audit'),
    }}, ensure_ascii=False, indent=2))
"""
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    path = "/tmp/remote_dump_hunt_result.py"
    with sftp.file(path, "w") as f:
        f.write(script)
    sftp.close()
    code, text = run(client, f"cd /opt/niteos && .venv/bin/python {path}", timeout=60)
    print(text.encode("cp1251", "replace").decode("cp1251", "replace"))
    client.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
