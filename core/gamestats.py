"""
core/gamestats.py
-----------------
Game mode memory (data/ folder only): saved profiles (clicker target and speed, break timer) and play statistics.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path


def _dir() -> Path:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "data"


def _load(name: str, default):
    try:
        return json.loads((_dir() / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(name: str, obj) -> None:
    try:
        _dir().mkdir(parents=True, exist_ok=True)
        (_dir() / name).write_text(json.dumps(obj), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------- profiles
def clean_profile(target: str, cps: int, break_on: bool, break_min: int) -> dict:
    return {"target": str(target)[:40], "cps": max(1, min(50, int(cps))), "break_on": bool(break_on),
            "break_min": max(10, min(180, int(break_min)))}


def profiles() -> dict:
    return _load("game_profiles.json", {})


def save_profile(name: str, target: str, cps: int, break_on: bool, break_min: int) -> bool:
    name = " ".join(name.split())[:30]
    if not name:
        return False
    data = profiles()
    if name not in data and len(data) >= 30:
        return False
    data[name] = clean_profile(target, cps, break_on, break_min)
    _save("game_profiles.json", data)
    return True


def delete_profile(name: str) -> None:
    data = profiles()
    if data.pop(name, None) is not None:
        _save("game_profiles.json", data)


# ---------------------------------------------------------------- statistics
def record_session(seconds: int, clicks: int, breaks: int, today: date | None = None) -> None:
    if seconds < 30:                      # opening and closing the mode straight away is not a session
        return
    day = (today or date.today()).isoformat()
    stats = _load("game_stats.json", {})
    d = stats.get(day, {"seconds": 0, "clicks": 0, "breaks": 0, "sessions": 0})
    d["seconds"] += int(seconds); d["clicks"] += int(clicks); d["breaks"] += int(breaks); d["sessions"] += 1
    stats[day] = d
    keep = sorted(stats)[-60:]
    _save("game_stats.json", {k: stats[k] for k in keep})


def summary(days: int = 7, today: date | None = None) -> str:
    today = today or date.today()
    stats = _load("game_stats.json", {})
    lines = [f"GAME MODE stats, last {days} days", ""]
    total = clicks = breaks = sessions = 0
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        d = stats.get(day)
        mins = (d["seconds"] // 60) if d else 0
        lines.append(f"{day}  {mins:>4} min  {'#' * min(40, mins // 10)}")
        if d:
            total += d["seconds"]; clicks += d["clicks"]; breaks += d["breaks"]; sessions += d["sessions"]
    lines.append("")
    if not sessions:
        lines.append("No sessions yet. Time in Game mode is saved when you leave it.")
    else:
        lines.append(f"Total {total // 3600} h {total % 3600 // 60} min in {sessions} session(s), {breaks} break reminder(s), {clicks} auto-clicks.")
    return "\n".join(lines)
