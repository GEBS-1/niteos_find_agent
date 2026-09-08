from sshutil import load_env, run, ssh_connect


def out(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def main() -> None:
    client = ssh_connect(load_env())
    cmd = r"""cd /opt/niteos && .venv/bin/python - <<'PY'
import inspect, aiogram.fsm.storage.base as b
print(b.__file__)
print([n for n in dir(b) if not n.startswith('_')])
print('--- BaseStorage methods ---')
for name, obj in inspect.getmembers(b.BaseStorage, predicate=inspect.isfunction):
    print(name, inspect.signature(obj))
PY"""
    code, text = run(client, cmd, timeout=20)
    print(code)
    print(out(text)[-4000:])
    client.close()


if __name__ == "__main__":
    main()
