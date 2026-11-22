"""
core/trust.py
---------------
Trust Levels + Intent Verification.

You choose how much EV may do without asking (Settings is in EV BRAIN -> Trust):
  careful  - asks before anything that changes something (files, keys, saved routines, clipboard...)
  balanced - asks before risky actions (typing or pressing keys for you, clicking in the browser, moving files...)  [default]
  trusting - only the actions that always ask (sending messages, deleting, closing apps) ask

When EV is about to do something that needs an OK, it first says IN PLAIN WORDS what it is about to do (the "intent"),
and only runs it after you agree. Tools that already ask for themselves are left alone.
"""
from __future__ import annotations

import inspect

from core import user_prefs

LEVELS = ("careful", "balanced", "trusting")

# risk 1 = changes something small and reversible, risk 2 = acts for you / hard to undo
RISK = {
    "create_folder": 1, "copy_file": 1, "write_clipboard": 1, "add_macro": 1, "remove_macro": 1, "save_task_chain": 1,
    "delete_task_chain": 1, "add_bookmark": 1, "remember": 1, "mute_microphone": 1, "add_note": 1, "add_todo": 1,
    "create_text_document": 1, "create_word_document": 1, "create_pdf_document": 1, "create_spreadsheet": 1,
    "save_contact": 1, "save_mission_space": 1,
    "type_text": 2, "press_key": 2, "browser_click": 2, "browser_type": 2, "move_file": 2, "rename_file": 2,
    "delete_note": 2, "forget": 2, "schedule_recurring": 2,
}

_WHY = {1: "it changes something on your computer", 2: "it acts for you and is hard to undo"}

_SAY = {
    "type_text": lambda a: f"type {_short(a.get('text'))} into whatever window is in front",
    "press_key": lambda a: f"press the key(s) {a.get('keys') or a.get('key') or ''} in whatever window is in front",
    "browser_click": lambda a: f"click {_short(a.get('target') or a.get('selector') or a.get('text'))} in the browser",
    "browser_type": lambda a: f"type {_short(a.get('text'))} into the browser page",
    "move_file": lambda a: f"move {_short(a.get('source') or a.get('path'))} to {_short(a.get('destination'))}",
    "rename_file": lambda a: f"rename {_short(a.get('path'))} to {_short(a.get('new_name'))}",
    "delete_note": lambda a: "delete a note",
    "forget": lambda a: f"forget {_short(a.get('key') or a.get('topic'))}",
    "schedule_recurring": lambda a: f"schedule a repeating task: {_short(a.get('message'))} at {a.get('time_of_day', '')}",
    "create_folder": lambda a: f"create the folder {_short(a.get('path') or a.get('name'))}",
    "copy_file": lambda a: f"copy {_short(a.get('source') or a.get('path'))}",
    "write_clipboard": lambda a: "replace what is on your clipboard",
    "save_task_chain": lambda a: f"save a routine called {_short(a.get('name'))}",
    "add_macro": lambda a: f"save a shortcut phrase {_short(a.get('trigger'))}",
}


def _short(v) -> str:
    v = "" if v is None else str(v)
    return f"'{v[:50]}{'…' if len(v) > 50 else ''}'" if v else "something"


def level() -> str:
    v = user_prefs.get("trust_level")
    return v if v in LEVELS else "balanced"


def set_level(v: str) -> None:
    if v in LEVELS:
        user_prefs.set_value("trust_level", v)


def threshold() -> int:
    """Actions with this risk or higher ask first."""
    return {"careful": 1, "balanced": 2, "trusting": 99}[level()]


def risk_of(name: str) -> int:
    return RISK.get(name, 0)


def asks_first() -> list[str]:
    t = threshold()
    return sorted(n for n, r in RISK.items() if r >= t)


def intent(name: str, arguments: dict) -> str:
    """One plain sentence saying what EV is about to do."""
    a = arguments or {}
    try:
        f = _SAY.get(name)
        if f:
            return "EV is about to " + f(a) + "."
    except Exception:
        pass
    from core import audit_log
    brief = audit_log._brief(a)
    return f"EV is about to run '{name.replace('_', ' ')}'" + (f" ({brief})" if brief else "") + "."


def needs_ok(name: str, arguments: dict, func) -> bool:
    """True when this call should wait for the user. Tools that have their own 'confirmed' step handle themselves."""
    r = risk_of(name)
    if r == 0 or r < threshold():
        return False
    if (arguments or {}).get("confirmed") is True:
        return False
    try:
        if "confirmed" in inspect.signature(func).parameters:
            return False
    except (TypeError, ValueError):
        pass
    return True


def question(name: str, arguments: dict) -> dict:
    r = risk_of(name)
    return {
        "confirmation_required": True,
        "message": (f"{intent(name, arguments)} I am asking because {_WHY.get(r, 'it is a sensitive action')}. "
                    "Tell the user exactly this and call the tool again with confirmed=true only if they say yes."),
    }
