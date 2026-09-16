"""Cost controls for hunt enrichment.

Safe default: cheap mode is ON. In this mode the hunt never calls RouterAI
web / owner / mass-verify paths, even if legacy HUNT_LLM_* flags are still
present on the server. This prevents accidental per-building LLM spend.

Exception: final card audit (HUNT_LLM_CARD_AUDIT, default ON) still runs one
cheap JSON-only RouterAI call per assembled card to catch bad object↔INN glue.

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


def llm_verify_enabled(*, force: bool = False) -> bool:
    """LLM presence/verdict pass without web.

    Mass hunt: off in cheap mode.
    Extra check: pass force=True from an explicit deep-verify request.
    """
    if force:
        return True
    if cheap_mode_enabled():
        return False
    return _flag("HUNT_LLM_VERIFY", "0")


def llm_card_audit_enabled() -> bool:
    """Final assembled-card audit (JSON only, no web).

    On by default even in cheap mode: one cheap end-gate per card to catch
    bad object↔INN glue (ТСЖ на чужой улице и т.п.). Disable with
    HUNT_LLM_CARD_AUDIT=0.
    """
    return _flag("HUNT_LLM_CARD_AUDIT", "1")


def llm_oneshot_enabled() -> bool:
    """Primary hunt path: one RouterAI web call → ready cards.

    Default ON. Works even when HUNT_CHEAP_MODE=1 — this is the intentional
    single paid research request per hunt. Disable with HUNT_LLM_ONESHOT=0
    to fall back to the classic maps/DaData pipeline.
    """
    return _flag("HUNT_LLM_ONESHOT", "1")


def llm_owner_enabled() -> bool:
    """LLM path for building→owner. Disabled in cheap mode."""
    if cheap_mode_enabled():
        return False
    return _flag("HUNT_LLM_OWNER", "0") or llm_web_enabled()


def llm_extra_check_enabled() -> bool:
    """Optional RouterAI post-check (no web). Requires cheap mode off + flag."""
    if cheap_mode_enabled():
        return False
    return _flag("HUNT_LLM_VERIFY", "0") or _flag("HUNT_LLM_EXTRA", "0")
