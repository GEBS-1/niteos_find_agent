# -*- coding: utf-8 -*-
"""Rebuild hunt-v5/.env for REAL mode (no demo mocks)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
OUT = ROOT / ".env"

TAKE = {
    "DADATA_API_KEY",
    "DADATA_SECRET_KEY",
    "ROUTERAI_API_KEY",
    "ROUTER_API_KEY",
    "ROUTERAI_BASE_URL",
    "ROUTERAI_MODEL",
    "OPENAI_API_KEY",
    "TWOGIS_API_KEY",
    "YANDEX_MAPS_API_KEY",
    "CADASTRE_API_URL",
    "CADASTRE_API_KEY",
    "PUBLIC_SEARCH_API_URL",
    "PUBLIC_SEARCH_API_KEY",
}


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> None:
    parent = parse_env(PARENT / ".env")
    merged = {
        "APP_NAME": "NITEOS Hunt V5",
        "DEMO_MODE": "0",
        "DATABASE_URL": "sqlite:///./data/niteos_hunt.db",
        "USER_AGENT": "NITEOS-Hunt-V5/1.0",
        "LLM_ENABLED": "0",
        "SALES_HIDE_PEOPLE_WITHOUT_CONTACTS": "1",
        "ROUTERAI_BASE_URL": "https://routerai.ru/api/v1",
        "ROUTERAI_MODEL": "openai/gpt-4o-mini",
    }
    for k in TAKE:
        if parent.get(k):
            merged[k] = parent[k]
    if merged.get("ROUTER_API_KEY") and not merged.get("ROUTERAI_API_KEY"):
        merged["ROUTERAI_API_KEY"] = merged["ROUTER_API_KEY"]
    OUT.write_text("\n".join(f"{k}={v}" for k, v in merged.items()) + "\n", encoding="utf-8")
    print("wrote", OUT)
    print("DEMO_MODE=0")
    print(
        "configured:",
        [k for k in TAKE if merged.get(k)],
    )
    print("primary_path: free (yandex/2gis_html/nominatim + dadata/list-org + nspd_soft)")
    print(
        "optional_unused:",
        [k for k in ("TWOGIS_API_KEY", "YANDEX_MAPS_API_KEY", "CADASTRE_API_URL") if not merged.get(k)],
    )


if __name__ == "__main__":
    main()
