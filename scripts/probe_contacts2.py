from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import re, httpx
from html import unescape
inn='6314030896'
h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36','Accept-Language':'ru-RU,ru;q=0.9'}
with httpx.Client(timeout=25, follow_redirects=True, headers=h) as c:
  r=c.get(f'https://www.list-org.com/search?type=inn&val={inn}')
  print('search', r.status_code, r.url)
  # find company links
  links=re.findall(r'href="(/company/\d+)"', r.text)
  print('links', links[:5])
  if not links:
    # alternate
    links=re.findall(r'href="(https://www\.list-org\.com/company/\d+)"', r.text)
    print('abs', links[:5])
  if links:
    path=links[0]
    u=path if path.startswith('http') else 'https://www.list-org.com'+path
    rr=c.get(u)
    print('company', rr.status_code, u)
    text=unescape(rr.text)
    phones=re.findall(r'(?:\+7|8)[\s\-\(]*\d{3}[\)\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}', text)
    # unique normalize
    print('phones raw', phones[:10])
    emails=re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', text)
    print('emails', [e for e in emails if 'list-org' not in e.lower()][:10])
    sites=re.findall(r'>(?:https?://)?([a-zA-Z0-9.-]+\.[a-z]{2,6})<', text)
    print('sites sample', sites[:10])
    # look for label Телефон
    m=re.search(r'Телефон[^<]{0,40}|тел(?:ефон)?[:\s]<[^>]+>([^<]+)', text, re.I)
    print('tel label', m.group(0)[:80] if m else None)
    # dump snippets around телефон
    for m in re.finditer(r'.{0,40}[Тт]елефон.{0,80}', text):
      print('snip', m.group(0).replace('\n',' ')[:120])
      if m.start()>5000: break
PY
"""
    code, text = run(client, cmd, timeout=60)
    Path(ROOT / "scripts" / "contact_probe2.txt").write_text(text, encoding="utf-8")
    print(text[:4000].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
