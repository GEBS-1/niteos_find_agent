from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import re, httpx
from urllib.parse import unquote, quote_plus
h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36','Accept-Language':'ru'}
company='ООО СКЛАД'
city='Самара'
fio='Лычев Сергей Николаевич'
inn='6314030896'

def ddg(c, q):
  r=c.get('https://html.duckduckgo.com/html/', params={'q':q})
  links=[]
  for x in re.findall(r'uddg=([^&"]+)', r.text):
    u=unquote(x)
    if u.startswith('http') and 'duckduckgo' not in u:
      links.append(u)
  # unique
  out=[]; seen=set()
  for u in links:
    if u not in seen:
      seen.add(u); out.append(u)
  return r.status_code, out[:12]

with httpx.Client(timeout=25, follow_redirects=True, headers=h) as c:
  queries=[
    f'{company} {city} официальный сайт',
    f'{company} {city} сайт',
    f'{company} {city} vk.com',
    f'{fio} {company}',
    f'{fio} директор {city}',
    f'{company} {city} site:t.me',
    f'{company} {city} телефон',
    f'ИНН {inn} телефон',
  ]
  for q in queries:
    code, links = ddg(c,q)
    print('Q', q)
    print(' ', code, links[:5])
  # 2gis html
  r=c.get(f'https://2gis.ru/samara/search/{quote_plus(company)}')
  print('2gis html', r.status_code, len(r.text))
  phones=re.findall(r'\+7[^<\"]{0,20}\d{2}', r.text)
  print('2gis phones sample', phones[:5])
  # check if json embedded
  m=re.search(r'phone[^,]{0,40}', r.text[:50000], re.I)
  print('phone snip', m.group(0) if m else None)
PY
"""
    code, text = run(client, cmd, timeout=120)
    Path(ROOT / "scripts" / "verify_probe2.txt").write_text(text, encoding="utf-8")
    print(text[:5000].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
