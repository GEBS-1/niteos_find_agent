from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import re, httpx
inn='6314030896'
name='ООО СКЛАД Самара'
h={'User-Agent':'Mozilla/5.0','Accept':'text/html'}
with httpx.Client(timeout=20, follow_redirects=True, headers=h) as c:
  for u in [
    f'https://www.list-org.com/search?type=inn&val={inn}',
    f'https://www.rusprofile.ru/search?query={inn}',
    f'https://2gis.ru/search/{inn}',
  ]:
    try:
      r=c.get(u)
      text=r.text
      phones=re.findall(r'\+?7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', text)
      sites=re.findall(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
      print(u, r.status_code, 'phones', phones[:5], 'len', len(text))
    except Exception as e:
      print('ERR', u, type(e).__name__, e)
PY
"""
    code, text = run(client, cmd, timeout=60)
    Path(ROOT / "scripts" / "contact_probe.txt").write_text(text, encoding="utf-8")
    print(text[:3000].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
