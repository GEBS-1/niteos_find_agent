from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""cd /opt/niteos && .venv/bin/python - <<'PY'
import os, asyncio, httpx
from dotenv import load_dotenv
load_dotenv('/opt/niteos/.env')
key = os.getenv('DADATA_API_KEY','')
headers={'Authorization': f'Token {key}', 'Content-Type':'application/json'}
URL='https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party'

async def go(label, body):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(URL, headers=headers, json=body)
        js = r.json()
        n = len(js.get('suggestions') or [])
        inns = [(s.get('data') or {}).get('inn') for s in (js.get('suggestions') or [])[:3]]
        print(label, r.status_code, 'n=', n, 'inns', inns)

async def main():
    base={'query':'завод','count':5,'status':['ACTIVE'],'type':'LEGAL'}
    await go('no_okved', base)
    await go('okved_multi', {**base, 'okved':['25','28','10']})
    await go('okved_25', {**base, 'okved':['25']})
    await go('okved_25_full', {**base, 'okved':['25.11']})
    await go('loc_ru', {**base, 'locations':[{'country_iso_code':'RU'}]})
    await go('loc_ru_okved', {**base, 'locations':[{'country_iso_code':'RU'}], 'okved':['25','28','10']})
    await go('tatarstan', {**base, 'locations':[{'country_iso_code':'RU','region':'Татарстан'}]})
asyncio.run(main())
PY"""
    code, text = run(client, cmd, timeout=60)
    print(code)
    print(out(text))
    client.close()


if __name__ == "__main__":
    main()
