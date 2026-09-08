from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)

BYPASS_HOST = "95.81.112.200"
BYPASS_KEY = "/root/.ssh/bypass_ed25519"
EDGE_LOG = "/opt/niteos-edge/cloudflared.log"

# Fallback paths on main VPS (legacy tunnel setups)
LOCAL_LOGS = (
    Path("/var/log/cloudflared-niteos.log"),
    Path("/opt/niteos/cloudflared.log"),
)


def _pick_url(text: str) -> str:
    found = URL_RE.findall(text or "")
    return found[-1].rstrip("/") if found else ""


def _url_from_local_logs() -> str:
    for path in LOCAL_LOGS:
        if not path.exists():
            continue
        try:
            url = _pick_url(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if url:
            return url
    return ""


async def _ssh_edge_log() -> str:
    cmd = [
        "ssh",
        "-i",
        BYPASS_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"root@{BYPASS_HOST}",
        f"grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' {EDGE_LOG} 2>/dev/null | tail -1",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
    except (asyncio.TimeoutError, OSError) as exc:
        log.warning("edge ssh failed: %s", exc)
        return ""
    if proc.returncode not in (0, 1):
        return ""
    return _pick_url(stdout.decode("utf-8", errors="replace"))


async def fetch_public_webapp_url() -> str:
    """Current HTTPS URL from Cloudflare quick tunnel on bypass host."""
    url = await _ssh_edge_log()
    if url:
        return url
    return _url_from_local_logs()


def update_env_webapp_url(env_path: Path, url: str) -> bool:
    """Write WEBAPP_URL to .env. Returns True if changed."""
    url = url.rstrip("/")
    if not url:
        return False
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    except OSError:
        lines = []
    old = ""
    out: list[str] = []
    for ln in lines:
        if ln.startswith("WEBAPP_URL="):
            old = ln.split("=", 1)[-1].strip()
            continue
        if ln.strip() or (out and out[-1].strip()):
            out.append(ln)
    out.append(f"WEBAPP_URL={url}")
    if old.rstrip("/") == url:
        return False
    try:
        env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("cannot write .env: %s", exc)
        return False
    return True
