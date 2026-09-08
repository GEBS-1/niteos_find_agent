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
  oid=c.get(f'https://bo.nalog.gov.ru/advanced-search/organizations/search?query={inn}&page=0').json()['content'][0]['id']
  periods=c.get(f'https://bo.nalog.gov.ru/nbo/organizations/{oid}/bfo').json()
  # pick year with gainSum
  periods=sorted(periods, key=lambda p: int(p.get('period') or 0), reverse=True)
  chosen=next((p for p in periods if p.get('gainSum') not in (None,)), periods[0])
  bid=chosen['id']
  print('chosen', chosen.get('period'), chosen.get('gainSum'), chosen.get('actives'))
  details=c.get(f'https://bo.nalog.gov.ru/nbo/bfo/{bid}/details').json()
  item=details[0] if isinstance(details, list) else details
  print('top_keys', sorted(item.keys()))
  for k in ('balance','financialResult','financialResultReport','cashFlow','explanation'):
    block=item.get(k)
    if isinstance(block, dict):
      print(k, 'keys', sorted(block.keys())[:40])
      # look for 2110/2400 style
      interesting={kk:vv for kk,vv in block.items() if any(x in kk.lower() for x in ('revenue','income','profit','gain','current2110','current2400','code2110','code2400','sum2110'))}
      if interesting:
        print(' interesting', interesting)
  # dump small subset of financialResult if present
  fr=item.get('financialResult') or item.get('financialResultReport') or {}
  print('fr_sample', json.dumps(fr, ensure_ascii=False)[:2000])
  bal=item.get('balance') or {}
  print('bal_sample', json.dumps({k:bal[k] for k in list(bal)[:25]}, ensure_ascii=False)[:1500])
PY
"""
    code, text = run(client, cmd, timeout=60)
    Path(ROOT / "scripts" / "fns_structure.json").write_text(text, encoding="utf-8")
    print(text[:5000].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
