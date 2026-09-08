from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import json, os, httpx
from dotenv import load_dotenv
load_dotenv('/opt/niteos/.env')
key = os.getenv('DADATA_API_KEY','')
headers = {'Authorization': f'Token {key}', 'Content-Type': 'application/json'}
inns = ['7707083893', '6672315362', '4101190411']
out = {}
with httpx.Client(timeout=20) as c:
    for inn in inns:
        r = c.post('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party', headers=headers, json={'query': inn, 'count': 1})
        items = (r.json() or {}).get('suggestions') or []
        data = (items[0].get('data') if items else {}) or {}
        out[inn] = {
            'status_code': r.status_code,
            'keys': sorted(data.keys()),
            'management': data.get('management'),
            'managers': data.get('managers'),
            'founders': data.get('founders'),
            'finance': data.get('finance'),
            'finance_history': (data.get('finance_history') or [])[:2],
            'employee_count': data.get('employee_count'),
            'phones': data.get('phones'),
            'emails': data.get('emails'),
        }
print(json.dumps(out, ensure_ascii=False, indent=2)[:8000])
PY
"""
    code, text = run(client, cmd, timeout=60)
    Path(ROOT / "scripts" / "dadata_enrich_probe.json").write_text(text, encoding="utf-8")
    print("code", code, "bytes", len(text))
    client.close()


if __name__ == "__main__":
    main()
