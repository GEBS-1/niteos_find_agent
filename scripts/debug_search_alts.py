from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    test = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import asyncio, re
from urllib.parse import unquote
import httpx

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

async def show(client, label, url, **kw):
    try:
        resp = await client.get(url, **kw)
    except Exception as e:
        print(label, 'ERR', e)
        return
    print(label, resp.status_code, len(resp.text))
    links = re.findall(r'href=[\"\'](https?://[^\"\']+)[\"\']', resp.text)
    print(' links', len(links), links[:6])
    print(' snip', resp.text[:160].replace('\n',' '))

async def main():
    async with httpx.AsyncClient(headers={'User-Agent': UA}, follow_redirects=True, timeout=25.0) as client:
        await show(client, 'bing', 'https://www.bing.com/search', params={'q': 'ООО ЯНДЕКС сайт'})
        await show(client, 'listorg', 'https://www.list-org.com/search?type=inn&val=7704217370')
        await show(client, 'checko', 'https://checko.ru/search?query=7704217370')
        await show(client, 'sbis', 'https://sbis.ru/contragents/7704217370')

asyncio.run(main())
PY
"""
    code, text = run(client, test, timeout=90)
    print("code", code)
    print(out(text)[-4000:])
    client.close()


if __name__ == "__main__":
    main()
