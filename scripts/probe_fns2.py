from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import json, httpx
inn='4101190411'
h={'User-Agent':'Mozilla/5.0','Accept':'application/json'}
with httpx.Client(timeout=25, follow_redirects=True, headers=h) as c:
  r=c.get(f'https://bo.nalog.gov.ru/advanced-search/organizations/search?query={inn}&page=0')
  content=(r.json() or {}).get('content') or []
  print('search_n', len(content))
  if not content:
    raise SystemExit
  oid=content[0]['id']
  print('id', oid)
  for path in [
    f'/nbo/organizations/{oid}',
    f'/nbo/organizations/{oid}/bfo',
    f'/nbo/organizations/{oid}/bfo/',
    f'/advanced-search/organizations/{oid}',
    f'/nbo/organizations/{oid}/details',
  ]:
    u='https://bo.nalog.gov.ru'+path
    rr=c.get(u)
    print(path, rr.status_code, rr.headers.get('content-type'), rr.text[:400].replace('\n',' '))
  # try periods
  rr=c.get(f'https://bo.nalog.gov.ru/nbo/organizations/{oid}/bfo/?period=2023')
  print('bfo2023', rr.status_code, rr.text[:500].replace('\n',' '))
  rr=c.get(f'https://bo.nalog.gov.ru/nbo/organizations/{oid}/bfo')
  print('bfo', rr.status_code, rr.text[:800].replace('\n',' '))
PY
"""
    code, text = run(client, cmd, timeout=60)
    Path(ROOT / "scripts" / "fns_probe2.txt").write_text(text, encoding="utf-8")
    print(text[:3500].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
