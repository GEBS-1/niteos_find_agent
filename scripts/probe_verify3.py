from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import json, re, httpx
from urllib.parse import quote_plus, unquote
h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36','Accept-Language':'ru'}
company='СКЛАД'
city='samara'
q='ООО СКЛАД Самара'
with httpx.Client(timeout=25, follow_redirects=True, headers=h) as c:
  r=c.get(f'https://2gis.ru/{city}/search/{quote_plus(q)}')
  text=r.text
  print('len', len(text), 'status', r.status_code)
  # find __INITIAL or similar json
  for pat in [r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', r'__CLOUDSHELL.*?(\{.*\"items\".*\})']:
    m=re.search(pat, text, re.S)
    print('pat', pat[:30], bool(m))
  # phones near company
  phones=re.findall(r'\+7\d{10}', text)
  from collections import Counter
  print('top phones', Counter(phones).most_common(8))
  # hrefs to firm
  firms=re.findall(r'href=\"(/[^\"]+/firm/[^\"]+)\"', text)
  print('firms', firms[:5])
  # bing
  rb=c.get('https://www.bing.com/search', params={'q': q + ' официальный сайт'})
  print('bing', rb.status_code, len(rb.text))
  blinks=re.findall(r'<a[^>]+href=\"(https?://[^\"]+)\"', rb.text)
  blinks=[u for u in blinks if 'bing.' not in u and 'microsoft.' not in u][:10]
  print('bing links', blinks)
  # brave
  try:
    br=c.get('https://search.brave.com/search', params={'q': q})
    print('brave', br.status_code, len(br.text))
  except Exception as e:
    print('brave err', e)
PY
"""
    code, text = run(client, cmd, timeout=90)
    Path(ROOT / "scripts" / "verify_probe3.txt").write_text(text, encoding="utf-8")
    print(text[:4500].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
