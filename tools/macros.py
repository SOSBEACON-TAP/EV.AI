"""
tools/macros.py
-----------------
Jarvis Pro custom voice/text macros.

Users can save short trigger phrases that expand into multi-step
instructions the brain already understands (or into a saved tool chain
name). Stored in data/macros.json — no secrets, just convenience.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_MAX_MACROS = 40
_MAX_TRIGGER = 80
_MAX_ACTION = 500


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _path() -> Path:
    return _root() / "data" / "macros.json"


def _load() -> list[dict]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [m for m in data if isinstance(m, dict) and "trigger" in m and "action" in m]
    except (OSError, ValueError):
        pass
    return []


def _save(macros: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(macros, indent=2), encoding="utf-8")


def list_macros() -> dict:
    """Return all saved macros."""
    macros = _load()
    return {
        "count": len(macros),
        "macros": [{"trigger": m["trigger"], "action": m["action"]} for m in macros],
    }


def add_macro(trigger: str, action: str) -> dict:
    """Save or update a macro. Trigger is matched case-insensitively as a phrase."""
    trigger = (trigger or "").strip()
    action = (action or "").strip()
    if not trigger or not action:
        return {"error": "Both trigger and action are required."}
    if len(trigger) > _MAX_TRIGGER:
        return {"error": f"Trigger too long (max {_MAX_TRIGGER} characters)."}
    if len(action) > _MAX_ACTION:
        return {"error": f"Action too long (max {_MAX_ACTION} characters)."}

    macros = _load()
    key = trigger.casefold()
    for m in macros:
        if m["trigger"].casefold() == key:
            m["action"] = action
            _save(macros)
            return {"status": "updated", "trigger": m["trigger"], "action": action}

    if len(macros) >= _MAX_MACROS:
        return {"error": f"Maximum of {_MAX_MACROS} macros reached. Delete one first."}

    macros.append({"trigger": trigger, "action": action})
    _save(macros)
    return {"status": "added", "trigger": trigger, "action": action}


def remove_macro(trigger: str) -> dict:
    """Delete a macro by trigger phrase (case-insensitive)."""
    trigger = (trigger or "").strip()
    if not trigger:
        return {"error": "Trigger is required."}
    macros = _load()
    key = trigger.casefold()
    kept = [m for m in macros if m["trigger"].casefold() != key]
    if len(kept) == len(macros):
        return {"error": f"No macro found for '{trigger}'."}
    _save(kept)
    return {"status": "removed", "trigger": trigger}


def match_macro(text: str) -> dict:
    """
    If the user text matches (or contains) a saved trigger, return the
    corresponding action so the brain can treat it as the real request.
    Exact phrase match preferred; otherwise substring match on whole words.
    """
    text = (text or "").strip()
    if not text:
        return {"matched": False}
    key = text.casefold()
    macros = _load()
    # Exact match first
    for m in macros:
        if m["trigger"].casefold() == key:
            return {"matched": True, "trigger": m["trigger"], "action": m["action"]}
    # Phrase match: the whole message must be the trigger, optionally with a
    # lead-in like "run" / "start" -- never just a word somewhere in a sentence.
    clean = re.sub(r"[^\w\s]", " ", key)
    clean = " ".join(clean.split())
    for m in macros:
        t = " ".join(re.sub(r"[^\w\s]", " ", m["trigger"].casefold()).split())
        if not t:
            continue
        for lead in ("", "run ", "start ", "do ", "activate ", "launch ", "begin ", "play "):
            if clean == lead + t:
                return {"matched": True, "trigger": m["trigger"], "action": m["action"]}
    return {"matched": False}
