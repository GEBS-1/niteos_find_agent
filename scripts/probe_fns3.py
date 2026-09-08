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
  oid=(r.json()['content'][0]['id'])
  periods=c.get(f'https://bo.nalog.gov.ru/nbo/organizations/{oid}/bfo').json()
  print('periods', json.dumps([{k:p.get(k) for k in ('id','period','gainSum','actives','mspCategory')} for p in periods], ensure_ascii=False))
  bid=periods[0]['id']
  for path in [
    f'/nbo/bfo/{bid}',
    f'/nbo/bfo/{bid}/details',
    f'/nbo/bfo/{bid}/forms',
    f'/nbo/organizations/{oid}/bfo/{bid}',
    f'/nbo/bfo/{bid}/info',
    f'/nbo/bfo/{bid}/summary',
  ]:
    rr=c.get('https://bo.nalog.gov.ru'+path)
    print(path, rr.status_code, rr.text[:500].replace('\n',' '))
PY
"""
    code, text = run(client, cmd, timeout=60)
    Path(ROOT / "scripts" / "fns_probe3.txt").write_text(text, encoding="utf-8")
    print(text[:4500].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
