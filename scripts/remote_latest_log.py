from __future__ import annotations

from sshutil import load_env, run, ssh_connect


REMOTE_SCRIPT = r"""
import sys
sys.path.insert(0, "/opt/niteos")
from app.db import SessionLocal
from app.models import Hunt, HuntResult, ObjectEntity, Company, Person, Contact

db = SessionLocal()
for h in db.query(Hunt).order_by(Hunt.id.desc()).limit(10):
    print("HUNT", h.id, h.city, h.query, h.status, h.progress, h.message)
    for r in db.query(HuntResult).filter(HuntResult.hunt_id == h.id):
        o = db.get(ObjectEntity, r.object_id)
        c = db.query(Company).filter(Company.inn == r.owner_company_inn).first() if r.owner_company_inn else None
        print("  OBJ", o.name, "|", o.source_provider, "| cad", o.cadastral_number, o.cadastre_status, "|", (o.cadastre_source or "")[:120])
        if c:
            people = db.query(Person).filter(Person.company_inn == c.inn).all()
            contacts = []
            for p in people:
                cs = db.query(Contact).filter(Contact.person_id == p.id).all()
                contacts.extend((p.full_name, p.role, x.contact_type, x.value, x.status, x.source_url) for x in cs)
            print("  OWNER", c.inn, c.name, "| rev", c.revenue, "| profit", c.profit, "| emp", c.employees, "| source", c.source)
            print("  PEOPLE", [(p.full_name, p.role) for p in people])
            print("  CONTACTS", contacts[:5])
        else:
            print("  OWNER", r.owner_company_inn or "-")
db.close()
"""


def main() -> None:
    client = ssh_connect(load_env())
    code, logs = run(client, "journalctl -u niteos-bot -n 100 --no-pager", timeout=40)
    print("--- journalctl ---")
    print(logs.encode("cp1251", "replace").decode("cp1251", "replace"))
    sftp = client.open_sftp()
    path = "/tmp/remote_latest_log.py"
    with sftp.file(path, "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()
    code, text = run(client, f"cd /opt/niteos && .venv/bin/python {path}", timeout=80)
    print("--- latest hunts ---")
    print(text.encode("cp1251", "replace").decode("cp1251", "replace"))
    client.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
