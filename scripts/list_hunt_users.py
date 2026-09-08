from sshutil import load_env, run, ssh_connect


def main() -> None:
    client = ssh_connect(load_env())
    code, text = run(
        client,
        "cd /opt/niteos && .venv/bin/python - <<'PY'\n"
        "import sqlite3\n"
        "db=sqlite3.connect('data/niteos.db')\n"
        "try:\n"
        "  rows=db.execute('select user_id, count(*) c from hunts group by user_id order by c desc').fetchall()\n"
        "  print('hunts_users', rows)\n"
        "except Exception as e:\n"
        "  print('err', e)\n"
        "PY",
        timeout=20,
    )
    print(code, text)
    client.close()


if __name__ == "__main__":
    main()
