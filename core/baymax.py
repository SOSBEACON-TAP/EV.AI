"""
core/baymax.py
----------------
Baymax mode's small health diary and helpers. Everything is saved on this PC in data/baymax.json.

Honest about what it is: EV AI is not a medical device and does not diagnose. Watch and band data
(Noise, NoiseFit and others) can't be read automatically: those makers offer no public connection.
So heart rate, steps and sleep are logged by hand here (type them in from the watch app), and Baymax
uses them in the daily overview.
"""
from __future__ import annotations

import json
import time
from datetime import date

from config import APP_ROOT

_PATH = APP_ROOT / "data" / "baymax.json"
KINDS = ("water", "break", "heart_rate", "steps", "sleep_hours", "mood")

EMERGENCY_NUMBERS = "India: 112 (all emergencies), 108 (ambulance), 100 (police). Elsewhere: 911 (US), 999 (UK), 112 (EU)."

_MOODS = {
    "sad": ("sad", "down", "depressed", "cry", "lonely", "hopeless", "miserable", "unhappy"),
    "stressed": ("stress", "anxious", "anxiety", "worried", "overwhelmed", "panic", "pressure", "nervous"),
    "tired": ("tired", "exhausted", "sleepy", "drained", "burnt out", "burned out", "no energy"),
    "angry": ("angry", "furious", "annoyed", "frustrated", "irritated", "mad"),
    "happy": ("happy", "great", "excited", "good day", "awesome", "wonderful", "glad"),
}


def _load() -> dict:
    try:
        d = json.loads(_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _today() -> str:
    return date.today().isoformat()


def log(kind: str, value=1) -> None:
    """Add to today's diary. water/break count up; the others store the latest value (mood keeps a list)."""
    if kind not in KINDS:
        raise KeyError(kind)
    d = _load()
    day = d.setdefault("days", {}).setdefault(_today(), {})
    if kind in ("water", "break"):
        day[kind] = int(day.get(kind, 0)) + int(value)
    elif kind == "mood":
        day.setdefault("mood", []).append([time.strftime("%H:%M"), str(value)])
    else:
        day[kind] = float(value)
    for old in sorted(d["days"])[:-30]:            # keep a month
        del d["days"][old]
    _save(d)


def today() -> dict:
    return dict(_load().get("days", {}).get(_today(), {}))


def detect_mood(text: str) -> str | None:
    """A simple word-based guess at how a typed message feels: sad, stressed, tired, angry or happy. None if unclear."""
    t = (text or "").lower()
    for mood, words in _MOODS.items():
        if any(w in t for w in words):
            return mood
    return None


def contacts() -> list[str]:
    return [c for c in _load().get("contacts", []) if isinstance(c, str)]


def set_contacts(emails: list[str]) -> None:
    d = _load()
    d["contacts"] = [e.strip() for e in emails if "@" in e][:5]
    _save(d)


def overview() -> str:
    """A plain-text daily wellness overview."""
    t = today()
    h = t.get("heart_rate")
    s = t.get("steps")
    sl = t.get("sleep_hours")
    moods = t.get("mood", [])
    lines = [
        f"Water: {int(t.get('water', 0))} glasses (goal 8)",
        f"Breaks taken: {int(t.get('break', 0))}",
        f"Sleep last night: {sl:g} h" if sl else "Sleep last night: not logged",
        f"Steps: {int(s)}" if s else "Steps: not logged",
        f"Heart rate: {h:g} bpm" if h else "Heart rate: not logged",
        f"Mood today: {moods[-1][1]} (at {moods[-1][0]})" if moods else "Mood today: not logged",
    ]
    return "\n".join(lines)
