"""
core/automation.py
---------------------
Stage 8: "smarter automation" — SQLite-backed storage for:
  - Task chains: a named sequence of tool calls the AI can define once
    and run later by name ("start work" -> open chrome, open notepad).
  - Scheduled tasks: recurring daily/weekly actions (an announcement,
    optionally paired with a tool call) that persist across restarts and
    get checked by a polling timer in ui/main_window.py.

Same separation as core/memory.py: this module only stores and queries
data. Actually *running* a task chain's steps, or a scheduled task's
tool call, needs a live ToolRouter — that happens in core/router.py
(for chains) and ui/main_window.py (for the scheduler poll), not here.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from config import settings

# Monday=0 .. Sunday=6, same as datetime.weekday() — kept as one source of
# truth so a weekday name typed by the AI/user maps to the same number
# the scheduler compares against.
WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _parse_weekday(text: str) -> int | None:
    key = (text or "").strip().lower()
    return WEEKDAYS.get(key)


def _validate_time_of_day(text: str) -> str | None:
    """Accepts 'HH:MM' 24-hour, returns it normalized or None if invalid."""
    try:
        parsed = datetime.strptime((text or "").strip(), "%H:%M")
    except ValueError:
        return None
    return parsed.strftime("%H:%M")


class AutomationStore:
    def __init__(self, db_path: str | None = None):
        path = Path(db_path) if db_path else settings.db_file
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS task_chains (
                name TEXT PRIMARY KEY,
                steps_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,            -- 'daily' or 'weekly'
                time_of_day TEXT NOT NULL,     -- 'HH:MM', 24-hour
                weekday INTEGER,               -- 0=Monday..6=Sunday, only for 'weekly'
                message TEXT NOT NULL,
                tool_name TEXT,
                tool_args_json TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                last_fired_date TEXT,          -- 'YYYY-MM-DD', guards against firing twice in one day
                created_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Task chains
    # ------------------------------------------------------------------
    def save_chain(self, name: str, steps: list) -> dict:
        key = (name or "").strip().lower()
        if not key:
            return {"error": "A task chain needs a name."}
        if not isinstance(steps, list) or not steps:
            return {"error": "steps must be a non-empty list of {tool, arguments} entries."}
        for step in steps:
            if not isinstance(step, dict) or "tool" not in step:
                return {"error": "Each step needs at least a 'tool' name."}

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("DELETE FROM task_chains WHERE name = ?", (key,))
        self._conn.execute(
            "INSERT INTO task_chains (name, steps_json, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(steps), now),
        )
        self._conn.commit()
        return {"status": "saved", "name": key, "step_count": len(steps)}

    def get_chain(self, name: str) -> list | None:
        row = self._conn.execute(
            "SELECT steps_json FROM task_chains WHERE name = ?", ((name or "").strip().lower(),)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def list_chains(self) -> dict:
        rows = self._conn.execute(
            "SELECT name, steps_json, created_at FROM task_chains ORDER BY name"
        ).fetchall()
        return {"chains": [
            {"name": r[0], "step_count": len(json.loads(r[1])), "created_at": r[2]} for r in rows
        ]}

    def delete_chain(self, name: str) -> dict:
        cur = self._conn.execute("DELETE FROM task_chains WHERE name = ?", ((name or "").strip().lower(),))
        self._conn.commit()
        if cur.rowcount == 0:
            return {"error": f"No task chain named '{name}'."}
        return {"status": "deleted", "name": name}

    # ------------------------------------------------------------------
    # Scheduled (recurring) tasks
    # ------------------------------------------------------------------
    def schedule_recurring(self, message: str, time_of_day: str, weekday: str = "",
                            tool_name: str = "", tool_args: dict | None = None) -> dict:
        time_norm = _validate_time_of_day(time_of_day)
        if time_norm is None:
            return {"error": "time_of_day must be 24-hour 'HH:MM', e.g. '09:30' or '18:00'."}

        weekday_num = None
        kind = "daily"
        if weekday:
            weekday_num = _parse_weekday(weekday)
            if weekday_num is None:
                return {"error": f"Unknown weekday '{weekday}'. Use a full day name like 'monday'."}
            kind = "weekly"

        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT INTO scheduled_tasks "
            "(kind, time_of_day, weekday, message, tool_name, tool_args_json, active, last_fired_date, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, NULL, ?)",
            (kind, time_norm, weekday_num, message, tool_name or None,
             json.dumps(tool_args) if tool_args else None, now),
        )
        self._conn.commit()
        return {
            "status": "scheduled", "id": cur.lastrowid, "kind": kind,
            "time_of_day": time_norm, "weekday": weekday or None, "message": message,
        }

    def list_scheduled(self) -> dict:
        rows = self._conn.execute(
            "SELECT id, kind, time_of_day, weekday, message, tool_name, active "
            "FROM scheduled_tasks ORDER BY time_of_day"
        ).fetchall()
        by_num = {v: k for k, v in WEEKDAYS.items()}
        return {"scheduled_tasks": [
            {
                "id": r[0], "kind": r[1], "time_of_day": r[2],
                "weekday": by_num.get(r[3]) if r[3] is not None else None,
                "message": r[4], "tool_name": r[5], "active": bool(r[6]),
            } for r in rows
        ]}

    def cancel_scheduled(self, task_id: int) -> dict:
        cur = self._conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
        self._conn.commit()
        if cur.rowcount == 0:
            return {"error": f"No scheduled task with id {task_id}."}
        return {"status": "cancelled", "id": task_id}

    def due_tasks(self, now: datetime) -> list[dict]:
        """Returns active tasks whose time_of_day matches the current
        minute, due today (daily, or weekly on today's weekday), and that
        haven't already fired today. Caller must call mark_fired() for
        each one returned, or it'll fire again next poll."""
        hhmm = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        weekday_today = now.weekday()

        rows = self._conn.execute(
            "SELECT id, kind, weekday, message, tool_name, tool_args_json "
            "FROM scheduled_tasks "
            "WHERE active = 1 AND time_of_day = ? "
            "AND (last_fired_date IS NULL OR last_fired_date != ?)",
            (hhmm, today),
        ).fetchall()

        due = []
        for r in rows:
            task_id, kind, weekday, message, tool_name, tool_args_json = r
            if kind == "weekly" and weekday != weekday_today:
                continue
            due.append({
                "id": task_id,
                "message": message,
                "tool_name": tool_name,
                "tool_args": json.loads(tool_args_json) if tool_args_json else {},
            })
        return due

    def mark_fired(self, task_id: int, date_str: str) -> None:
        self._conn.execute(
            "UPDATE scheduled_tasks SET last_fired_date = ? WHERE id = ?", (date_str, task_id)
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
