"""
core/app_usage.py
-------------------
App Usage Insights, local only: how long each program was in the FRONT
(the window you were actually using), stored per day in data/usage.db. No
window titles, no screenshots, nothing leaves your computer.

This module is storage + reporting (no Qt). The ticking that feeds it lives in
ui/usage_tracker.py. Every call opens its own short SQLite connection, so it is
safe to use from the UI thread and from the AI's worker thread at once.
"""

import sqlite3
from datetime import date, timedelta

from config import APP_ROOT
from core import user_prefs

DB_PATH = APP_ROOT / "data" / "usage.db"

# friendly names for common programs (key = program name without .exe, lower-case)
_NAMES = {
    "chrome": "Google Chrome", "msedge": "Microsoft Edge", "firefox": "Firefox", "brave": "Brave",
    "code": "VS Code", "pycharm64": "PyCharm", "idea64": "IntelliJ IDEA", "devenv": "Visual Studio",
    "windowsterminal": "Windows Terminal", "cmd": "Command Prompt", "powershell": "PowerShell",
    "python": "Python", "pythonw": "Python", "notepad": "Notepad", "notepad++": "Notepad++",
    "explorer": "File Explorer", "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint",
    "onenote": "OneNote", "acrord32": "Adobe Reader", "acrobat": "Adobe Acrobat",
    "spotify": "Spotify", "vlc": "VLC", "discord": "Discord", "steam": "Steam",
    "whatsapp": "WhatsApp", "telegram": "Telegram", "teams": "Microsoft Teams", "zoom": "Zoom",
    "slack": "Slack", "arduino ide": "Arduino IDE", "arduino": "Arduino IDE",
}

CATEGORIES = {
    "Coding": {"code", "pycharm64", "idea64", "devenv", "sublime_text", "notepad++", "windowsterminal", "cmd",
               "powershell", "python", "pythonw", "arduino", "arduino ide", "githubdesktop", "androidstudio64"},
    "Study": {"winword", "powerpnt", "excel", "onenote", "acrord32", "acrobat", "sumatrapdf", "anki",
              "notion", "obsidian", "zotero", "kindle"},
    "Browsing": {"chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "chromium"},
    "Entertainment": {"spotify", "vlc", "discord", "steam", "netflix", "epicgameslauncher", "whatsapp",
                      "telegram", "scratch 3", "scratch"},
}
CATEGORY_ORDER = ["Coding", "Study", "Browsing", "Entertainment", "Other"]


def _key(program: str) -> str:
    p = (program or "").strip().lower()
    return p[:-4] if p.endswith(".exe") else p


def friendly(program: str) -> str:
    k = _key(program)
    if k in _NAMES:
        return _NAMES[k]
    return (program[:-4] if program.lower().endswith(".exe") else program).strip().title() or "Unknown"


def category_of(program: str) -> str:
    k = _key(program)
    for cat, names in CATEGORIES.items():
        if k in names:
            return cat
    return "Other"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("CREATE TABLE IF NOT EXISTS usage (day TEXT NOT NULL, app TEXT NOT NULL, "
                 "seconds REAL NOT NULL, PRIMARY KEY (day, app))")
    return conn


def excluded_apps() -> set:
    raw = str(user_prefs.get("usage_excluded"))
    return {_key(x) for x in raw.replace(";", ",").split(",") if x.strip()}


def add_time(program: str, seconds: float, day: date | None = None) -> None:
    if seconds <= 0 or not program:
        return
    key = _key(program)
    if key in excluded_apps():
        return
    day_s = (day or date.today()).isoformat()
    conn = _connect()
    try:
        conn.execute("INSERT INTO usage (day, app, seconds) VALUES (?, ?, ?) "
                     "ON CONFLICT(day, app) DO UPDATE SET seconds = seconds + excluded.seconds",
                     (day_s, key, float(seconds)))
        conn.commit()
    finally:
        conn.close()


def _range(period: str) -> tuple[str, str, str]:
    """(start_iso, end_iso, label) for 'today' | 'yesterday' | 'week' | 'month'."""
    today = date.today()
    p = (period or "today").lower()
    if p == "yesterday":
        d = today - timedelta(days=1)
        return d.isoformat(), d.isoformat(), "yesterday"
    if p in ("week", "7days", "this week", "last 7 days"):
        return (today - timedelta(days=6)).isoformat(), today.isoformat(), "the last 7 days"
    if p in ("month", "30days", "last 30 days"):
        return (today - timedelta(days=29)).isoformat(), today.isoformat(), "the last 30 days"
    return today.isoformat(), today.isoformat(), "today"


def app_totals(period: str = "today") -> list[tuple[str, float]]:
    """[(program key, seconds)] biggest first."""
    start, end, _ = _range(period)
    conn = _connect()
    try:
        rows = conn.execute("SELECT app, SUM(seconds) FROM usage WHERE day BETWEEN ? AND ? "
                            "GROUP BY app ORDER BY 2 DESC", (start, end)).fetchall()
    finally:
        conn.close()
    return [(a, float(s)) for a, s in rows]


def category_totals(period: str = "today") -> dict:
    totals = {c: 0.0 for c in CATEGORY_ORDER}
    for app, secs in app_totals(period):
        totals[category_of(app)] += secs
    return totals


def daily_totals(days: int = 7) -> list[tuple[str, float]]:
    """[(iso day, seconds)] oldest first, zero-filled."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    conn = _connect()
    try:
        rows = dict(conn.execute("SELECT day, SUM(seconds) FROM usage WHERE day >= ? GROUP BY day",
                                 (start.isoformat(),)).fetchall())
    finally:
        conn.close()
    return [((start + timedelta(days=i)).isoformat(), float(rows.get((start + timedelta(days=i)).isoformat(), 0)))
            for i in range(days)]


def clear_history() -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM usage")
        conn.commit()
    finally:
        conn.close()


def remove_app(program: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM usage WHERE app = ?", (_key(program),))
        conn.commit()
    finally:
        conn.close()


def fmt_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    if minutes < 1:
        return f"{int(seconds)}s" if seconds >= 1 else "0m"
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


# ---- AI tool ------------------------------------------------------------------
def get_usage_summary(period: str = "today", category: str = "") -> dict:
    """Time spent in each application (foreground), top apps and category totals."""
    if not user_prefs.get("usage_tracking") and not app_totals("month"):
        return {"error": "App usage tracking is turned off, and nothing has been recorded yet. "
                         "It can be switched on in Settings → App Usage Insights."}
    _, _, label = _range(period)
    apps = app_totals(period)
    cats = category_totals(period)
    wanted = (category or "").strip().title()
    if wanted and wanted in cats:
        apps = [(a, s) for a, s in apps if category_of(a) == wanted]
    total = sum(s for _, s in apps)
    if not apps:
        return {"period": label, "total": "0m", "message": f"No app usage recorded for {label} yet."}
    return {
        "period": label,
        "tracking_on": bool(user_prefs.get("usage_tracking")),
        "total": fmt_duration(total),
        "top_apps": [{"app": friendly(a), "time": fmt_duration(s), "category": category_of(a)}
                     for a, s in apps[:8]],
        "by_category": {c: fmt_duration(s) for c, s in cats.items() if s > 0},
    }
