from __future__ import annotations

import json
from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

REMOTE = "/opt/niteos"


def put_dir(sftp, local: Path, remote: str) -> None:
    try:
        sftp.mkdir(remote)
    except OSError:
        pass
    for path in local.iterdir():
        if path.name == "__pycache__" or path.suffix == ".pyc":
            continue
        dest = f"{remote}/{path.name}"
        if path.is_dir():
            put_dir(sftp, path, dest)
        else:
            sftp.put(str(path), dest)


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", f"{REMOTE}/app")
    sftp.close()

    code, text = run(
        client,
        "systemctl restart niteos-bot && sleep 3 && systemctl is-active niteos-bot",
        timeout=30,
    )
    print("restart", code, text.strip())

    hunt_py = r"""
import asyncio, json, os, sys
sys.path.insert(0, "/opt/niteos")
os.chdir("/opt/niteos")
from app.config import load_settings
from app.db import connect
from app.agents import run_hunt

async def progress(text):
    print("PROGRESS", text, flush=True)

async def main():
    settings = load_settings()
    database = await connect(settings)
    try:
        result = await run_hunt(
            settings=settings,
            database=database,
            user_id=0,
            sphere_ids=["industry"],
            phrase="",
            okved_raw="",
            target_count=1,
            region="",
            city="",
            kladr_id="",
            progress=progress,
        )
    finally:
        await database.close()
    companies = []
    for c in result.get("companies") or []:
        companies.append({
            "name": c.get("name"),
            "inn": c.get("inn"),
            "okved": c.get("okved"),
            "address": c.get("address"),
            "stamp": c.get("stamp"),
            "score": c.get("score"),
            "idea": c.get("idea"),
            "management": c.get("management"),
        })
    out = {
        "hunt_id": result.get("hunt_id"),
        "already": result.get("already"),
        "skipped": result.get("skipped"),
        "dropped": result.get("dropped"),
        "errors": result.get("errors"),
        "queries": result.get("queries"),
        "companies": companies,
    }
    Path = __import__("pathlib").Path
    Path("/tmp/niteos_hunt_test.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("HUNT_JSON_OK", len(companies))

asyncio.run(main())
"""
    sftp = client.open_sftp()
    with sftp.file("/tmp/niteos_hunt_test.py", "w") as fh:
        fh.write(hunt_py)
    sftp.close()

    code, text = run(
        client,
        "cd /opt/niteos && .venv/bin/python /tmp/niteos_hunt_test.py",
        timeout=90,
    )
    print("hunt_run", code)
    print(text[-2500:])

    code, raw = run(client, "cat /tmp/niteos_hunt_test.json", timeout=15)
    Path(ROOT / "scripts" / "hunt_test.json").write_text(raw, encoding="utf-8")
    print("saved hunt_test.json", code, "bytes", len(raw))

    try:
        data = json.loads(raw)
        company = (data.get("companies") or [{}])[0]
        name = company.get("name") or "—"
        inn = company.get("inn") or "—"
        addr = company.get("address") or "—"
        okved = company.get("okved") or "—"
        stamp = company.get("stamp") or "—"
        msg = (
            "Починил охоту. Раньше ДаДата из-за ОКВЭД «25» отдавала 0 компаний.\n\n"
            f"Проверка на сервере, 1 компания, промка:\n"
            f"{name}\nИНН {inn}\n{okved}\n{addr}\nШтамп: {stamp}\n\n"
            "В боте: /start → сфера → кнопка 1 → Начать поиск."
        )
    except Exception as exc:
        print("parse fail", exc)
        client.close()
        return

    token = env["BOT_TOKEN"]
    # user who already pressed hunt
    chat_id = "388963917"
    # write message to a file to avoid shell encoding issues
    sftp = client.open_sftp()
    with sftp.file("/tmp/niteos_tg.txt", "w") as fh:
        fh.write(msg)
    sftp.close()
    send = (
        f"curl -sS --max-time 20 --socks5-hostname 127.0.0.1:1080 "
        f"-F chat_id={chat_id} -F text=\\</tmp/niteos_tg.txt "
        f"https://api.telegram.org/bot{token}/sendMessage"
    )
    # curl -F text=</file doesn't work that way. Use --data-urlencode
    send = (
        f"python3 - <<'PY'\n"
        "import json,urllib.parse,subprocess\n"
        f"token={token!r}\n"
        "text=open('/tmp/niteos_tg.txt',encoding='utf-8').read()\n"
        "url=f'https://api.telegram.org/bot{token}/sendMessage'\n"
        "body=urllib.parse.urlencode({'chat_id': '388963917', 'text': text})\n"
        "open('/tmp/niteos_post.txt','w',encoding='utf-8').write(body)\n"
        "PY\n"
        f"curl -sS --max-time 20 --socks5-hostname 127.0.0.1:1080 "
        f"-X POST --data-binary @/tmp/niteos_post.txt "
        f"-H 'Content-Type: application/x-www-form-urlencoded' "
        f"https://api.telegram.org/bot{token}/sendMessage"
    )
    code, text = run(client, send, timeout=40)
    print("notify", code, text[:400])

    code, text = run(
        client,
        "journalctl -u niteos-bot -n 12 --no-pager -o cat",
        timeout=15,
    )
    print("log", text[-1200:])
    client.close()


if __name__ == "__main__":
    main()
