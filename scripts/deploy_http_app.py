from pathlib import Path

from sshutil import ROOT, load_env, run, ssh_connect

PROXY_MARKER = "NITEOS_PROXY_START"
PROXY_BLOCK = r'''
// NITEOS_PROXY_START
import http from 'http';
app.use('/niteos', (req, res) => {
  const dest = req.originalUrl.replace(/^\/niteos/, '') || '/';
  const headers = { ...req.headers, host: '127.0.0.1:8088' };
  headers['x-forwarded-for'] = req.ip || req.socket?.remoteAddress || '';
  const proxy = http.request(
    { hostname: '127.0.0.1', port: 8088, path: dest, method: req.method, headers },
    (up) => { res.writeHead(up.statusCode || 502, up.headers); up.pipe(res); }
  );
  proxy.on('error', () => { if (!res.headersSent) res.status(502).end('niteos down'); });
  req.pipe(proxy);
});
// NITEOS_PROXY_END
'''


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
    host = env["SSH_HOST"]
    client = ssh_connect(env)
    sftp = client.open_sftp()
    put_dir(sftp, ROOT / "app", "/opt/niteos/app")
    put_dir(sftp, ROOT / "web", "/opt/niteos/web")
    sftp.close()

    setup = r"""
python3 - <<'PY'
import os, re, secrets, pathlib, shutil
js_path = pathlib.Path('/opt/affiliate-factory/server.js')
text = js_path.read_text(encoding='utf-8')
if 'NITEOS_PROXY_START' not in text:
    shutil.copy(js_path, '/opt/affiliate-factory/server.js.bak-niteos')
    needle = 'const app = express();\n'
    block = '''
// NITEOS_PROXY_START
import http from 'http';
app.use('/niteos', (req, res) => {
  const dest = req.originalUrl.replace(/^\/niteos/, '') || '/';
  const headers = { ...req.headers, host: '127.0.0.1:8088' };
  headers['x-forwarded-for'] = req.ip || req.socket?.remoteAddress || '';
  const proxy = http.request(
    { hostname: '127.0.0.1', port: 8088, path: dest, method: req.method, headers },
    (up) => { res.writeHead(up.statusCode || 502, up.headers); up.pipe(res); }
  );
  proxy.on('error', () => { if (!res.headersSent) res.status(502).end('niteos down'); });
  req.pipe(proxy);
});
// NITEOS_PROXY_END
'''
    if needle not in text:
        raise SystemExit('express needle missing')
    # import http must be top-level in ESM - put import with other imports
    if "import http from 'http'" not in text:
        text = text.replace("import cors from 'cors';\n", "import cors from 'cors';\nimport http from 'http';\n")
    block = block.replace("import http from 'http';\n", "")
    text = text.replace(needle, needle + block)
    js_path.write_text(text, encoding='utf-8')
    print('proxy_patched')
else:
    print('proxy_exists')

envp = pathlib.Path('/opt/niteos/.env')
env = envp.read_text(encoding='utf-8')
# token
if 'WEBAPP_TOKEN=' not in env:
    token = secrets.token_hex(16)
    env += f'\nWEBAPP_TOKEN={token}\n'
    print('token_created')
else:
    print('token_exists')
# public url using host from existing SSH is set by outer script via extra lines
envp.write_text(env, encoding='utf-8')
print('env_ok')
PY
"""
    code, text = run(client, setup, timeout=20)
    print("patch", code, out(text)[-800:])

    public = f"http://{host}:3010/niteos"
    # set WEBAPP_URL without printing it in a way we repeat later... we will print 'url_set'
    seturl = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"url={public!r}\n"
        "p=Path('/opt/niteos/.env')\n"
        "lines=[ln for ln in p.read_text(encoding='utf-8').splitlines() if not ln.startswith('WEBAPP_URL=')]\n"
        "lines.append('WEBAPP_URL='+url)\n"
        "if not any(ln.startswith('WEBAPP_PORT=') for ln in lines):\n"
        "    lines.append('WEBAPP_PORT=8088')\n"
        "p.write_text('\\n'.join(lines)+'\\n', encoding='utf-8')\n"
        "print('url_set')\n"
        "PY"
    )
    code, text = run(client, seturl, timeout=15)
    print("url", code, out(text))

    code, text = run(
        client,
        "systemctl disable --now niteos-tunnel || true; "
        "pm2 restart affiliate-factory; "
        "systemctl restart niteos-bot; "
        "sleep 5; "
        "systemctl is-active niteos-bot; "
        "curl -sS -o /dev/null -w 'local_root=%{http_code}\\n' --max-time 8 http://127.0.0.1:8088/; "
        "curl -sS -o /dev/null -w 'proxy=%{http_code}\\n' --max-time 8 http://127.0.0.1:3010/niteos/; "
        "curl -sS -o /dev/null -w 'aff=%{http_code}\\n' --max-time 8 http://127.0.0.1:3010/",
        timeout=40,
    )
    print("svc", code, out(text)[-1500:])

    # token for test hunt - read on server, don't print
    hunt = r"""
python3 - <<'PY'
import json, os, urllib.request
from pathlib import Path
token=''
for ln in Path('/opt/niteos/.env').read_text().splitlines():
    if ln.startswith('WEBAPP_TOKEN='):
        token=ln.split('=',1)[1].strip()
req=urllib.request.Request(
    'http://127.0.0.1:3010/niteos/api/meta',
    headers={'X-Niteos-Token': token},
)
meta=json.load(urllib.request.urlopen(req, timeout=8))
print('meta_okved', len(meta.get('okved') or []), 'cities', len(meta.get('cities') or []))
body=json.dumps({'phrase':'склад','okved':['52.10'],'city':'Казань','count':1,'token':token}).encode()
req=urllib.request.Request(
    'http://127.0.0.1:3010/niteos/api/hunt',
    data=body,
    headers={'Content-Type':'application/json','X-Niteos-Token': token},
    method='POST',
)
print('post', urllib.request.urlopen(req, timeout=8).read().decode())
PY
"""
    code, text = run(client, hunt, timeout=25)
    print("hunt", code, out(text)[-800:])

    token_env = env["BOT_TOKEN"]
    msg = (
        "Готово мини-приложение.\n\n"
        "Жми /start → «Открыть охоту».\n"
        "Там: вся Россия или город из списка, ОКВЭД из ~190 кодов или свой, сколько взять.\n"
        "Кнопка «Начать охоту» — агенты сами ищут и проверяют, на экране список."
    )
    sftp = client.open_sftp()
    with sftp.file("/tmp/niteos_tg.txt", "w") as fh:
        fh.write(msg)
    sftp.close()
    send = (
        "python3 - <<'PY'\n"
        "import urllib.parse\n"
        f"token={token_env!r}\n"
        "text=open('/tmp/niteos_tg.txt',encoding='utf-8').read()\n"
        "open('/tmp/niteos_post.txt','w',encoding='utf-8').write("
        "urllib.parse.urlencode({'chat_id': '388963917', 'text': text}))\n"
        "PY\n"
        f"curl -sS --max-time 20 --socks5-hostname 127.0.0.1:1080 "
        f"-X POST --data-binary @/tmp/niteos_post.txt "
        f"-H 'Content-Type: application/x-www-form-urlencoded' "
        f"https://api.telegram.org/bot{token_env}/sendMessage"
    )
    code, text = run(client, send, timeout=30)
    print("notify", code, text[:200])

    Path(ROOT / "scripts" / "webapp_url.txt").write_text(public + "\n", encoding="utf-8")
    client.close()
    print("done")


if __name__ == "__main__":
    main()
