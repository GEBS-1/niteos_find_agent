#!/bin/bash
# Standalone sync: bypass cloudflared log -> /opt/niteos/.env -> restart bot if URL changed
set -euo pipefail
ENV=/opt/niteos/.env
KEY=/root/.ssh/bypass_ed25519
HOST=95.81.112.200
LOG=/opt/niteos-edge/cloudflared.log

NEW=$(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=8 "root@$HOST" \
  "grep -oE 'https://[a-z0-9-]+\\.trycloudflare\\.com' $LOG 2>/dev/null | tail -1" || true)
NEW=${NEW//$'\r'/}
NEW=${NEW//$'\n'/}
[ -n "$NEW" ] || exit 0

OLD=$(grep -E '^WEBAPP_URL=' "$ENV" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r\n' || true)
if [ "$OLD" = "$NEW" ]; then
  exit 0
fi

python3 - <<PY
from pathlib import Path
env = Path("$ENV")
url = "$NEW"
lines = [ln for ln in env.read_text(encoding="utf-8").splitlines() if not ln.startswith("WEBAPP_URL=")]
lines.append("WEBAPP_URL=" + url)
env.write_text("\\n".join(lines).rstrip() + "\\n", encoding="utf-8")
print("updated", url)
PY

systemctl kill -s SIGKILL niteos-bot 2>/dev/null || true
sleep 1
systemctl reset-failed niteos-bot 2>/dev/null || true
systemctl start niteos-bot
