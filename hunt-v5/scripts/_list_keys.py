# -*- coding: utf-8 -*-
from pathlib import Path

p = Path(__file__).resolve().parents[2] / ".env"
for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    k = k.strip()
    v = v.strip().strip('"').strip("'")
    if any(
        x in k.upper()
        for x in (
            "DADATA",
            "ROUTER",
            "OPENAI",
            "TWOGIS",
            "2GIS",
            "YANDEX",
            "CADASTRE",
            "SERPER",
            "VK",
            "BOT",
        )
    ):
        print(f"{k}={'SET' if v else 'EMPTY'} len={len(v)}")
