"""
core/shorts.py
--------------
Counts the short videos you scroll through (YouTube Shorts, Instagram Reels, TikTok) so you can see how much
time goes into them. The Chrome extension reports one count per short; the totals stay on this PC.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

SITES = {"youtube": "YouTube Shorts", "instagram": "Instagram Reels", "tiktok": "TikTok"}
MILESTONE = 25            # EV says something every 25 shorts


def _path() -> Path:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "data" / "shorts_count.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def record(site: str, n: int = 1, path: Path | None = None, today: str | None = None) -> tuple[int, bool]:
    """Adds n shorts. Returns (today's total, True if a new milestone of 25 was just passed)."""
    path = path or _path()
    if site not in SITES:
        return total(path=path, today=today), False
    day = today or date.today().isoformat()
    data = _load(path)
    days = data.setdefault(day, {})
    before = sum(days.values())
    days[site] = days.get(site, 0) + max(0, min(int(n), 50))
    after = sum(days.values())
    for old in sorted(data)[:-30]:            # keep the last 30 days
        data.pop(old, None)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
    return after, (after // MILESTONE) > (before // MILESTONE)


def total(path: Path | None = None, today: str | None = None) -> int:
    return sum(_load(path or _path()).get(today or date.today().isoformat(), {}).values())


def summary(path: Path | None = None, today: str | None = None) -> str:
    day = _load(path or _path()).get(today or date.today().isoformat(), {})
    if not day:
        return "You haven't scrolled any shorts today."
    parts = ", ".join(f"{n} on {SITES[s]}" for s, n in day.items() if s in SITES)
    return f"You have scrolled {sum(day.values())} shorts today: {parts}."
