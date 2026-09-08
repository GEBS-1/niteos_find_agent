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

async def main():
    async with httpx.AsyncClient(
        headers={'User-Agent': 'Mozilla/5.0 (compatible; NiteosBot/1.0)'},
        follow_redirects=True,
        timeout=20.0,
    ) as client:
        for url, params in [
            ('https://html.duckduckgo.com/html/', {'q': 'ООО ЯНДЕКС Москва сайт'}),
            ('https://lite.duckduckgo.com/lite/', {'q': 'ООО ЯНДЕКС Москва сайт'}),
        ]:
            try:
                resp = await client.get(url, params=params)
            except Exception as e:
                print('ERR', url, e)
                continue
            print('URL', url, 'status', resp.status_code, 'len', len(resp.text))
            uddg = re.findall(r'uddg=([^&\"]+)', resp.text)
            href = re.findall(r'href=\"(https?://[^\"]+)\"', resp.text)[:8]
            print('uddg', len(uddg), [unquote(x)[:60] for x in uddg[:3]])
            print('href', href[:5])
            print('snippet', resp.text[:200].replace('\n',' '))

asyncio.run(main())
PY
"""
    code, text = run(client, test, timeout=60)
    print("code", code)
    print(out(text))
    client.close()


if __name__ == "__main__":
    main()
