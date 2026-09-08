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
# mid-size / known LLCs
inns = ['9729288550', '7707049388', '5027310986', '2462206345', '5402534361']
out = {}
with httpx.Client(timeout=20) as c:
    for inn in inns:
        r = c.post('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party', headers=headers, json={'query': inn})
        items = (r.json() or {}).get('suggestions') or []
        if not items:
            out[inn] = {'empty': True, 'status': r.status_code}
            continue
        data = items[0].get('data') or {}
        out[inn] = {
            'name': items[0].get('value'),
            'management': data.get('management'),
            'managers_n': len(data.get('managers') or []),
            'founders_n': len(data.get('founders') or []),
            'founders_sample': (data.get('founders') or [])[:2],
            'managers_sample': (data.get('managers') or [])[:2],
            'finance': data.get('finance'),
            'finance_history_n': len(data.get('finance_history') or []),
            'finance_history_sample': (data.get('finance_history') or [])[:1],
            'employee_count': data.get('employee_count'),
            'capital': data.get('capital'),
            'phones': data.get('phones'),
            'emails': data.get('emails'),
            'sites': data.get('sites'),
        }
print(json.dumps(out, ensure_ascii=False, indent=2)[:12000])
PY
"""
    code, text = run(client, cmd, timeout=60)
    Path(ROOT / "scripts" / "dadata_enrich_probe2.json").write_text(text, encoding="utf-8")
    print("code", code)
    print(text[:3000].encode("ascii", "replace").decode("ascii"))
    client.close()


if __name__ == "__main__":
    main()
