from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    test = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import asyncio, re, html as htmllib, base64
from urllib.parse import urlparse, parse_qs, unquote
import httpx

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

def unwrap(url: str) -> str:
    url = htmllib.unescape(url)
    if url.startswith('/ck/'):
        url = 'https://www.bing.com' + url
    if 'bing.com/ck/' in url:
        qs = parse_qs(urlparse(url).query)
        raw = (qs.get('u') or [''])[0]
        if raw.startswith('a1'):
            pad = raw[2:] + '=' * ((4 - len(raw[2:]) % 4) % 4)
            try:
                return base64.urlsafe_b64decode(pad).decode('utf-8', 'replace')
            except Exception as e:
                return f'ERR:{e}:{raw[:40]}'
    return url

async def main():
    async with httpx.AsyncClient(headers={'User-Agent': UA}, follow_redirects=True, timeout=25.0) as client:
        for q in ['ozon.ru официальный сайт', 'site:vk.com ozon', 'site:t.me ozon']:
            resp = await client.get('https://www.bing.com/search', params={'q': q})
            print('Q', q, 'status', resp.status_code)
            # save algo blocks
            cites = re.findall(r'<cite[^>]*>(.*?)</cite>', resp.text, flags=re.I|re.S)
            print(' cites', [re.sub('<[^>]+>','',c)[:80] for c in cites[:5]])
            hrefs = re.findall(r'<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"', resp.text, flags=re.I)
            print(' h2hrefs', len(hrefs))
            for h in hrefs[:5]:
                print('  ', unwrap(h)[:120])
            # also try data-url
            data = re.findall(r'data-url=\"([^\"]+)\"', resp.text)
            print(' data-url', data[:3])

        # list-org parse sites/phones for known company
        page = await client.get('https://www.list-org.com/company/54442')
        sites = re.findall(r"class='[^']*site[^']*'[^>]*>(https?://[^<]+)</a>", page.text)
        sites2 = re.findall(r"class=\"[^\"]*site[^\"]*\"[^>]*>(https?://[^<]+)</a>", page.text)
        print('parsed sites', sites, sites2)
        phones = re.findall(r"/phone/(\d[\d\-]+)", page.text)
        print('phone paths', phones[:5])

asyncio.run(main())
PY
"""
    code, text = run(client, test, timeout=90)
    print("code", code)
    print(out(text)[-5000:])
    client.close()


if __name__ == "__main__":
    main()
