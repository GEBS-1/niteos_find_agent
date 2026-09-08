from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import json, httpx
inn='4101190411'
urls=[
 f'https://bo.nalog.gov.ru/advanced-search/organizations/search?query={inn}&page=0',
 f'https://bo.nalog.gov.ru/nbo/organizations/?inn={inn}',
 f'https://pb.nalog.ru/search-proc.json',
]
with httpx.Client(timeout=20, follow_redirects=True, headers={'User-Agent':'Mozilla/5.0'}) as c:
  for u in urls[:2]:
    try:
      r=c.get(u)
      print('GET', u, r.status_code, r.headers.get('content-type'), r.text[:300].replace('\n',' '))
    except Exception as e:
      print('ERR', u, type(e).__name__, e)
  # pb search
  try:
    r=c.post('https://pb.nalog.ru/search-proc.json', data={'mode':'search-all','queryAll':inn,'page':'1','pageSize':'10'})
    print('PB', r.status_code, r.text[:500])
  except Exception as e:
    print('PBERR', type(e).__name__, e)
PY
"""
    code, text = run(client, cmd, timeout=60)
    Path(ROOT / "scripts" / "fns_probe.txt").write_text(text, encoding="utf-8")
    print(text[:2500].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
