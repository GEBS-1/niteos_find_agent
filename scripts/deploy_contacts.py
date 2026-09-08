from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def put_dir(sftp, local: Path, remote: str) -> None:
    try:
        sftp.mkdir(remote)
    except OSError:
        pass
    for path in local.iterdir():
        if path.name == "__pycache__" or path.suffix == ".pyc":
            continue
        dest = f"{remote}/{path.name}"
        if path.is_dir():
            put_dir(sftp, path, dest)
        else:
            sftp.put(str(path), dest)


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    sftp.close()

    code, text = run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; systemctl start niteos-bot; "
        "sleep 3; systemctl is-active niteos-bot",
        timeout=40,
    )
    print("bot", code, out(text)[-200:])

    test = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import asyncio, json
from app.contacts import enrich_contacts

async def main():
    party = {
        'inn': '7704217370',
        'name': 'ООО "ИНТЕРНЕТ РЕШЕНИЯ"',
        'address': '123112, г Москва, Пресненская наб, д 10',
        'management': 'Багдасарян Арман Рубикович',
        'management_post': 'ГЕНЕРАЛЬНЫЙ ДИРЕКТОР',
        'phones': [],
        'emails': [],
        'sites': [],
    }
    party = await enrich_contacts(party)
    print('hits', party.get('online_hits'))
    print('routes', len(party['contact_routes']))
    for key, item in (party.get('presence') or {}).items():
        if key == 'checks':
            continue
        print(key, item.get('status'), (item.get('value') or '')[:60])
    for r in party['contact_routes'][:8]:
        print('-', r['title'], r.get('status'), r['url'][:80])
    open('/tmp/niteos_contacts.json','w',encoding='utf-8').write(json.dumps(party, ensure_ascii=False, indent=2))

asyncio.run(main())
PY
"""
    code, text = run(client, test, timeout=40)
    print("test", code)
    print(out(text)[-2000:])
    code, raw = run(client, "cat /tmp/niteos_contacts.json", timeout=10)
    Path(ROOT / "scripts" / "contacts_sample.json").write_text(raw, encoding="utf-8")
    client.close()
    print("done")


if __name__ == "__main__":
    main()
