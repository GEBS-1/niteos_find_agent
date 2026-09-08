"""Cost controls for hunt enrichment.

Default: no RouterAI web plugin / no LLM verify — keep a card under ~5 ₽.
Set HUNT_LLM_WEB=1 / HUNT_LLM_VERIFY=1 only for expensive deep research.
"""
from __future__ import annotations

import os


def _flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def llm_web_enabled() -> bool:
    """RouterAI plugins.id=web — ~2+ ₽ per call, often 3–5× per building."""
    return _flag("HUNT_LLM_WEB", "0")


def llm_verify_enabled() -> bool:
    """LLM presence/verdict pass without web — still burns tokens."""
    return _flag("HUNT_LLM_VERIFY", "0")


def llm_owner_enabled() -> bool:
    """LLM path for building→owner. Off by default (DaData/list-org first)."""
    return _flag("HUNT_LLM_OWNER", "0") or llm_web_enabled()
