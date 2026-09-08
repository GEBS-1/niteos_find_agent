"""Cost controls for hunt enrichment.

Safe default: cheap mode is ON. In this mode the hunt never calls RouterAI
web / owner / verify paths, even if legacy HUNT_LLM_* flags are still present
on the server. This prevents accidental per-building LLM spend.

To deliberately enable deep LLM research set::

    HUNT_CHEAP_MODE=0

and then enable only the exact expensive feature you need, for example
HUNT_LLM_VERIFY=1 or HUNT_LLM_OWNER=1.
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


def cheap_mode_enabled() -> bool:
    """Hard safety switch: no paid LLM research during the mass hunt."""
    return _flag("HUNT_CHEAP_MODE", "1")


def llm_web_enabled() -> bool:
    """RouterAI web plugin. Disabled while cheap mode is active."""
    if cheap_mode_enabled():
        return False
    return _flag("HUNT_LLM_WEB", "0")


def llm_verify_enabled() -> bool:
    """LLM presence/verdict pass without web. Disabled in cheap mode."""
    if cheap_mode_enabled():
        return False
    return _flag("HUNT_LLM_VERIFY", "0")


def llm_owner_enabled() -> bool:
    """LLM path for building→owner. Disabled in cheap mode."""
    if cheap_mode_enabled():
        return False
    return _flag("HUNT_LLM_OWNER", "0") or llm_web_enabled()
