from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    key = env["DADATA_API_KEY"]
    cmds = [
        (
            "systemctl is-active niteos-bot; journalctl -u niteos-bot --since '2026-08-26 07:00:00' --no-pager -o cat | tail -n 80",
            30,
        ),
        (
            "cd /opt/niteos && .venv/bin/python -c \"import sqlite3; c=sqlite3.connect('data/niteos.db'); "
            "print('hunts'); "
            "[print(r) for r in c.execute('select id,user_id,phrase,spheres_json,okved,region,city,target_count,status,created_at from hunts')]; "
            "print('companies', list(c.execute('select count(*) from companies'))); "
            "print('results', list(c.execute('select hunt_id,count(*) from hunt_results group by hunt_id')));\"",
            20,
        ),
        (
            "cd /opt/niteos && .venv/bin/python - <<'PY'\n"
            "import os, asyncio, httpx\n"
            "from pathlib import Path\n"
            "from dotenv import load_dotenv\n"
            "load_dotenv('/opt/niteos/.env')\n"
            "key = os.getenv('DADATA_API_KEY','')\n"
            "print('key_len', len(key))\n"
            "async def main():\n"
            "    headers={'Authorization': f'Token {key}', 'Content-Type':'application/json'}\n"
            "    async with httpx.AsyncClient(timeout=20) as c:\n"
            "        for label, body in [\n"
            "            ('plain', {'query':'склад','count':3,'status':['ACTIVE'],'type':'LEGAL'}),\n"
            "            ('okved', {'query':'склад','count':3,'status':['ACTIVE'],'type':'LEGAL','okved':['52.10']}),\n"
            "            ('geo', {'query':'склад','count':3,'status':['ACTIVE'],'type':'LEGAL','locations':[{'country_iso_code':'RU','region':'Татарстан'}]}),\n"
            "            ('one', {'query':'1','count':3,'status':['ACTIVE'],'type':'LEGAL'}),\n"
            "        ]:\n"
            "            r = await c.post('https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party', headers=headers, json=body)\n"
            "            js = r.json() if r.headers.get('content-type','').startswith('application/json') else {}\n"
            "            n = len(js.get('suggestions') or [])\n"
            "            names = [s.get('value') for s in (js.get('suggestions') or [])[:2]]\n"
            "            print(label, r.status_code, 'n=', n, names, str(js)[:180] if r.status_code>=400 else '')\n"
            "asyncio.run(main())\n"
            "PY",
            60,
        ),
    ]
    for cmd, timeout in cmds:
        print("\n=====")
        try:
            code, text = run(client, cmd, timeout=timeout)
            print("code", code)
            print(out(text)[-5000:])
        except Exception as exc:
            print("ERR", type(exc).__name__, exc)
    client.close()


if __name__ == "__main__":
    main()
