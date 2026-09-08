from pathlib import Path

from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    test = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import asyncio
from app.contacts import enrich_contacts

async def main():
    party = {
        'inn': '7704217370',
        'name': 'ООО "ЯНДЕКС"',
        'address': '119021, г Москва, ул Льва Толстого, д 16',
        'management': 'Савиновская Елена Алексеевна',
        'management_post': 'ГЕНЕРАЛЬНЫЙ ДИРЕКТОР',
        'phones': [],
        'emails': [],
        'sites': [],
    }
    party = await enrich_contacts(party)
    print('hits', party.get('online_hits'))
    for key, item in (party.get('presence') or {}).items():
        if key == 'checks':
            continue
        print(key, item.get('status'), (item.get('value') or '')[:70])
    for line in (party.get('presence') or {}).get('checks') or []:
        print('check:', line)

asyncio.run(main())
PY
"""
    code, text = run(client, test, timeout=80)
    print("code", code)
    print(out(text))
    client.close()


if __name__ == "__main__":
    main()
