from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect


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


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    env = load_env()
    client = ssh_connect(env)
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    sftp.close()

    code, text = run(
        client,
        "systemctl kill -s SIGKILL niteos-bot || true; sleep 1; systemctl reset-failed niteos-bot || true; "
        "systemctl start niteos-bot; sleep 4; systemctl is-active niteos-bot",
        timeout=40,
    )
    print("bot", code, out(text)[-300:])

    hunt = r"""
cd /opt/niteos && .venv/bin/python - <<'PY'
import asyncio, json, os
from app.config import load_settings
from app.db import connect
from app.agents import run_hunt

async def progress(t):
    print('P', t.replace('\n',' / ')[:120], flush=True)

async def main():
    settings = load_settings()
    database = await connect(settings)
    try:
        result = await run_hunt(
            settings=settings,
            database=database,
            user_id=0,
            sphere_ids=[],
            phrase='склад',
            okved_raw='52.10',
            target_count=1,
            region='',
            city='',
            progress=progress,
        )
    finally:
        await database.close()
    open('/tmp/niteos_enrich.json','w',encoding='utf-8').write(json.dumps(result, ensure_ascii=False, indent=2))
    c=(result.get('companies') or [{}])[0]
    print('NAME', c.get('name'))
    print('MGMT', c.get('management_label') or c.get('management'))
    print('POST', c.get('management_post'))
    print('FOUNDERS', c.get('founders'))
    print('REV', c.get('revenue_text'), c.get('finance_year'))
    print('PROFIT', c.get('profit_text'))
    print('ASSETS', c.get('assets_text'))
    print('PHONES', c.get('phones'))
    print('OK')

asyncio.run(main())
PY
"""
    code, text = run(client, hunt, timeout=120)
    print("hunt", code)
    print(out(text)[-2500:])
    code, raw = run(client, "cat /tmp/niteos_enrich.json", timeout=15)
    Path(ROOT / "scripts" / "enrich_hunt.json").write_text(raw, encoding="utf-8")
    print("saved", len(raw))
    client.close()


if __name__ == "__main__":
    main()
