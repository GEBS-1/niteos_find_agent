from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import re, httpx
from html import unescape
h={'User-Agent':'Mozilla/5.0','Accept-Language':'ru'}
with httpx.Client(timeout=25, follow_redirects=True, headers=h) as c:
  r=c.get('https://2gis.ru/samara/firm/70000001100024742')
  text=unescape(r.text)
  print('status', r.status_code, 'len', len(text))
  print('title', re.search(r'<title>([^<]+)</title>', text).group(1)[:120] if re.search(r'<title>([^<]+)</title>', text) else None)
  phones=re.findall(r'\+7\d{10}', text)
  print('phones', list(dict.fromkeys(phones))[:8])
  # websites
  sites=re.findall(r'https?://(?!2gis\.|vk\.com/images|mc\.yandex)([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\"\s]*)', text)
  print('sites', list(dict.fromkeys(sites))[:10])
  # name candidates
  for pat in [r'\"name\":\"([^\"]{3,80})\"', r'itemprop=\"name\"[^>]*>([^<]+)']:
    vals=re.findall(pat, text)[:5]
    print(pat[:30], vals)
PY
"""
    code, text = run(client, cmd, timeout=40)
    print(text[:3000].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
