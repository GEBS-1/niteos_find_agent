import urllib.request

from sshutil import load_env


def probe(url: str) -> str:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as r:
            return f"{r.status} {r.geturl()[:40]} {len(r.read(80))}"
    except Exception as exc:
        return type(exc).__name__ + " " + str(exc)[:80]


def main() -> None:
    host = load_env()["SSH_HOST"]
    for port in (22, 80, 443, 3010, 3780, 8088, 8443):
        print(port, probe(f"http://{host}:{port}/"))


if __name__ == "__main__":
    main()
