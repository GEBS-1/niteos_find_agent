"""Deploy LLM agent-3 and smoke-test RouterAI + factory/ozon cases."""
from __future__ import annotations

import json
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
    env = load_env()
    key = env.get("ROUTERAI_API_KEY") or env.get("ROUTER_API_KEY") or ""
    if not key:
        raise SystemExit("No ROUTER_API_KEY / ROUTERAI_API_KEY in local .env")
    base = env.get("ROUTERAI_BASE_URL") or "https://routerai.ru/api/v1"
    model = env.get("ROUTERAI_MODEL") or "openai/gpt-4o-mini"

    client = ssh_connect(env)
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    sftp.close()

    # Merge RouterAI into server .env without printing secrets
    sync = f"""
python3 - <<'PY'
from pathlib import Path
p = Path('/opt/niteos/.env')
text = p.read_text(encoding='utf-8') if p.exists() else ''
lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith('#')]
keys = {{}}
for ln in lines:
    if '=' in ln:
        k,v = ln.split('=',1)
        keys[k.strip()] = v.strip()
keys['ROUTERAI_API_KEY'] = {key!r}
keys['ROUTER_API_KEY'] = {key!r}
keys['ROUTERAI_BASE_URL'] = {base!r}
keys['ROUTERAI_MODEL'] = {model!r}
out = []
# keep unknown keys + our router keys
order = list(keys.keys())
for k in order:
    out.append(f'{{k}}={{keys[k]}}')
p.write_text('\\n'.join(out) + '\\n', encoding='utf-8')
print('env_keys', len(keys), 'has_router', bool(keys.get('ROUTERAI_API_KEY')))
PY
"""
    code, text = run(client, sync, timeout=20)
    print("env", code, out(text)[-200:])

    code, text = run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; "
        "systemctl reset-failed niteos-bot || true; systemctl start niteos-bot; "
        "sleep 2; systemctl is-active niteos-bot",
        timeout=40,
    )
    print("bot", code, out(text)[-80:])

    test = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import asyncio, json, os
from dotenv import load_dotenv
load_dotenv('/opt/niteos/.env')
from app.llm import RouterAI
from app.contacts import enrich_contacts
from app.config import load_settings

async def main():
    s = load_settings()
    llm = RouterAI(s.router_api_key, base_url=s.router_base_url, model=s.router_model)
    print('llm_available', llm.available, 'model', s.router_model)
    ping = await llm.chat([
        {'role':'user','content':'Ответь одним словом: ok'}
    ], max_tokens=8)
    print('ping', ping[:40])

    # factory trap + zavod.ru
    factory = {
        'inn': '1650123456',
        'name': 'ООО "ЗАВОД ЦХ ПРОМ"',
        'address': '420000, Республика Татарстан, г Казань',
        'management': 'Иванов Иван Иванович',
        'phones': [], 'emails': [], 'sites': [],
    }
    factory = await enrich_contacts(factory, llm=llm)
    print('FACTORY site', factory['presence']['site'])
    print('FACTORY vk', factory['presence']['vk_company'])
    print('FACTORY tg', factory['presence']['telegram'])
    print('FACTORY llm', 'Агент 3' in ' '.join(factory['presence'].get('checks') or []))
    for c in factory['presence'].get('checks') or []:
        if 'LLM' in c or 'Агент 3' in c:
            print(' check', c[:160])

    ozon = {
        'inn': '7704217370',
        'name': 'ООО "ИНТЕРНЕТ РЕШЕНИЯ"',
        'address': '123112, г Москва, Пресненская наб, д 10',
        'management': 'Багдасарян Арман Рубикович',
        'phones': [], 'emails': [], 'sites': [],
    }
    ozon = await enrich_contacts(ozon, llm=llm)
    print('OZON site', ozon['presence']['site'])
    print('OZON phone', ozon['presence']['phone'])
    print('OZON vk', ozon['presence']['vk_company'])
    print('OZON tg', ozon['presence']['telegram'])
    for c in ozon['presence'].get('checks') or []:
        if 'LLM' in c or 'Агент 3' in c:
            print(' check', c[:160])

    Path = __import__('pathlib').Path
    Path('/tmp/niteos_llm_test.json').write_text(
        json.dumps({'factory': factory, 'ozon': ozon}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    await llm.aclose()

asyncio.run(main())
PY
"""
    code, text = run(client, test, timeout=180)
    print("test", code)
    print(out(text)[-4500:])
    code, raw = run(client, "cat /tmp/niteos_llm_test.json", timeout=15)
    (ROOT / "scripts" / "llm_test_sample.json").write_text(raw, encoding="utf-8")
    client.close()
    print("saved scripts/llm_test_sample.json")


if __name__ == "__main__":
    main()
