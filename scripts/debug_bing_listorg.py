from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    test = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import asyncio, re, html as htmllib
from urllib.parse import unquote, urlparse, parse_qs
import httpx

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

def unwrap_bing(url: str) -> str:
    if 'bing.com/ck/a' in url or 'bing.com/ck/' in url:
        # u=a1aHR0cHM6Ly... base64-ish
        qs = parse_qs(urlparse(url).query)
        for key in ('u', 'r'):
            raw = (qs.get(key) or [''])[0]
            if not raw:
                continue
            # bing prefixes with a1
            if raw.startswith('a1'):
                import base64
                pad = raw[2:] + '=' * ((4 - len(raw[2:]) % 4) % 4)
                try:
                    return base64.urlsafe_b64decode(pad).decode('utf-8', 'replace')
                except Exception:
                    pass
            if raw.startswith('http'):
                return raw
    return url

async def main():
    async with httpx.AsyncClient(headers={'User-Agent': UA}, follow_redirects=True, timeout=25.0) as client:
        resp = await client.get('https://www.bing.com/search', params={'q': 'site:vk.com ООО ЯНДЕКС Москва'})
        print('bing status', resp.status_code)
        raw_hrefs = re.findall(r'href=\"(/ck/a\?[^\"]+|https?://[^\"]+)\"', resp.text)
        cleaned = []
        for href in raw_hrefs:
            if href.startswith('/ck/'):
                href = 'https://www.bing.com' + href
            href = htmllib.unescape(href)
            href = unwrap_bing(href)
            if href.startswith('http'):
                cleaned.append(href)
        print('cleaned sample:')
        for u in cleaned[:15]:
            print('-', u[:100])

        resp2 = await client.get('https://www.list-org.com/search?type=inn&val=7704217370')
        print('listorg status', resp2.status_code)
        # company links like /company/123
        cos = re.findall(r'href=[\"\']/company/(\d+)[\"\']', resp2.text)
        print('companies', cos[:5])
        if cos:
            page = await client.get(f'https://www.list-org.com/company/{cos[0]}')
            print('company page', page.status_code, len(page.text))
            sites = re.findall(r'href=[\"\'](https?://[^\"\']+)[\"\'][^>]*>\s*сайт', page.text, flags=re.I)
            sites2 = re.findall(r'Сайт[^<]*</[^>]+>\s*<[^>]+href=[\"\'](https?://[^\"\']+)[\"\']', page.text, flags=re.I)
            phones = re.findall(r'\+7[\d\s\-\(\)]{10,20}', page.text)
            emails = re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', page.text)
            print('sites1', sites[:3], 'sites2', sites2[:3])
            print('phones', phones[:3], 'emails', emails[:3])
            # dump interesting lines
            for line in page.text.splitlines():
                low = line.lower()
                if 'сайт' in low or 'телефон' in low or 'e-mail' in low or 'email' in low or 'vk.com' in low:
                    print('L:', line.strip()[:180])

asyncio.run(main())
PY
"""
    code, text = run(client, test, timeout=90)
    print("code", code)
    print(out(text)[-5000:])
    client.close()


if __name__ == "__main__":
    main()
