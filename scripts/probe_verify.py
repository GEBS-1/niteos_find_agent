from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import re, httpx
from urllib.parse import quote_plus, unquote
q_company='СКЛАД Самара'
q_person='Лычев Сергей Николаевич Самара'
h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36','Accept-Language':'ru-RU,ru;q=0.9'}
with httpx.Client(timeout=20, follow_redirects=True, headers=h) as c:
  # DuckDuckGo html
  for label,q in [('co',q_company),('pe',q_person)]:
    r=c.get('https://html.duckduckgo.com/html/', params={'q':q})
    print('ddg', label, r.status_code, len(r.text))
    links=re.findall(r'uddg=([^&"]+)', r.text)
    decoded=[unquote(x) for x in links][:8]
    print(' links', decoded)
  # VK search people/communities via m.vk
  for section,q in [('communities',q_company),('people',q_person)]:
    r=c.get('https://m.vk.com/search', params={'c[q]':q,'c[section]':section})
    print('vk', section, r.status_code, len(r.text), 'login' in r.text.lower())
    hrefs=re.findall(r'href="(/[^"]+)"', r.text)
    interesting=[h for h in hrefs if any(x in h for x in ('/club','/public','/id','/wall'))][:10]
    print(' hrefs', interesting)
  # 2gis catalog open api sometimes
  r=c.get('https://catalog.api.2gis.com/3.0/items', params={'q':q_company,'page_size':5,'fields':'items.contact_groups,items.address_name'})
  print('2gis', r.status_code, r.text[:300])
PY
"""
    code, text = run(client, cmd, timeout=90)
    Path(ROOT / "scripts" / "verify_probe.txt").write_text(text, encoding="utf-8")
    print(text[:4500].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
