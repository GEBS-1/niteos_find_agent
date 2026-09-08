import json
from pathlib import Path

d = json.load(open("scripts/local_hunt_test.json", encoding="utf-8"))
cos = d["full"].get("companies") or []
lines = [f"n={len(cos)}"]
for x in cos:
    pr = x.get("presence") or {}

    def v(k: str) -> str:
        return (pr.get(k) or {}).get("value") or ""

    lines.append("---")
    lines.append(f"name: {x.get('name')}")
    lines.append(f"inn: {x.get('inn')}")
    lines.append(f"stamp: {x.get('stamp_label')}")
    lines.append(f"phone: {v('phone')}")
    lines.append(f"email: {v('email')}")
    lines.append(f"site: {v('site')}")
    lines.append(f"vk: {v('vk_company')}")
    lines.append(f"tg: {v('telegram')}")
    lines.append(f"wa: {v('whatsapp')}")
    lines.append(f"recommend: {(pr.get('recommend') or {}).get('value')}")
    photos = x.get("photos") or []
    lines.append(f"photos_n: {len(photos)}")
    for ph in photos[:4]:
        lines.append(f"  photo: {ph}")
    kp = x.get("kp") or {}
    lines.append(f"kp_title: {kp.get('title')}")
    lines.append(f"kp_msg: {(kp.get('message_short') or '')[:220]}")

Path("scripts/local_hunt_readable.txt").write_text("\n".join(lines), encoding="utf-8")
print("ok", len(cos))
