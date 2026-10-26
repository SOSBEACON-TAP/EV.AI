"""
core/audit_log.py
-------------------
A running history of what EV has *done* — every tool it ran (opened an
app, sent an email, set a reminder...), when, with what (shortened, and
secrets masked), and whether it worked. Shown in Settings -> Privacy
center. Saved to data/automation_history.jsonl, capped at 500 entries.
Logging can never break a tool: every failure here is swallowed.
"""

import json
import threading
import time

from config import APP_ROOT

_PATH = APP_ROOT / "data" / "automation_history.jsonl"
_LOCK = threading.Lock()
_MAX_ENTRIES = 500
_SECRET_WORDS = ("password", "passwd", "secret", "token", "key", "pin")
_QUIET_TOOLS = {"get_datetime", "get_system_info", "list_reminders", "list_todos", "list_notes",
                "list_contacts", "recall"}   # read-only lookups would just add noise


def _brief(arguments: dict) -> str:
    parts = []
    for name, value in (arguments or {}).items():
        if name == "confirmed":
            continue
        if any(word in name.lower() for word in _SECRET_WORDS):
            value = "••••"
        elif name.lower() in ("body", "text", "content", "message"):
            value = f"<{len(str(value))} chars>"
        else:
            value = str(value)
            if len(value) > 50:
                value = value[:47] + "…"
        parts.append(f"{name}={value}")
    return ", ".join(parts)


def record(tool: str, arguments: dict, ok: bool, note: str = "") -> None:
    if tool in _QUIET_TOOLS:
        return
    try:
        entry = {"t": time.time(), "tool": tool, "args": _brief(arguments), "ok": ok}
        if note:
            entry["note"] = note[:120]
        with _LOCK:
            _PATH.parent.mkdir(parents=True, exist_ok=True)
            with _PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            _trim()
    except Exception:
        pass


def _trim() -> None:
    try:
        lines = _PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_ENTRIES + 50:
            _PATH.write_text("\n".join(lines[-_MAX_ENTRIES:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def recent(limit: int = 60) -> list[dict]:
    try:
        lines = _PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return list(reversed(out))   # newest first


def clear() -> None:
    with _LOCK:
        try:
            _PATH.unlink()
        except OSError:
            pass
