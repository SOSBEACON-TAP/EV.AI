"""
tools/reminders.py
---------------------
One-off timers/reminders. They are saved to data/personal.json, so a
reminder set for tomorrow still fires after EV is closed and reopened
(if it came due while EV was closed, it's announced as missed on the
next start).

Firing a reminder needs to interrupt the UI (announce it out loud), but
this module deliberately has no Qt/UI code in it, same as every other
tools/*.py file. Instead, ui/main_window.py registers a callback at
startup via register_callback(); when a timer fires, that callback gets
called with the reminder's message. main_window.py is responsible for
making that callback thread-safe (it does this by handing us a Qt
Signal's .emit method, which Qt safely queues onto the main thread even
when called from this module's background timer thread).
"""

import threading
import time
from datetime import datetime, timedelta

from core import personal_store as store

_on_reminder_fired = None  # callback(message: str), set via register_callback()
_active_timers: dict[int, threading.Timer] = {}
_meta: dict[int, tuple[float, str]] = {}   # id -> (due epoch seconds, message)


def register_callback(callback) -> None:
    """Called once by ui/main_window.py at startup to receive fired reminders."""
    global _on_reminder_fired
    _on_reminder_fired = callback


def _fire(reminder_id: int, message: str) -> None:
    _active_timers.pop(reminder_id, None)
    _meta.pop(reminder_id, None)
    store.remove("reminders", reminder_id)
    if _on_reminder_fired is not None:
        _on_reminder_fired(message)


def _schedule(reminder_id: int, due: float, message: str, delay: float | None = None) -> None:
    delay = max(0.0, due - time.time()) if delay is None else delay
    t = threading.Timer(delay, _fire, args=(reminder_id, message))
    t.daemon = True
    _active_timers[reminder_id] = t
    _meta[reminder_id] = (due, message)
    t.start()


def restore() -> int:
    """Re-arm reminders saved by a previous run. Call once after
    register_callback(). Overdue ones are announced (marked as missed)
    a few seconds after start-up. Returns how many were restored."""
    now = time.time()
    count = 0
    for item in store.items("reminders"):
        rid, due, message = item["id"], float(item.get("due", 0)), item.get("message", "Reminder")
        if rid in _active_timers:
            continue
        if due <= now:
            _schedule(rid, due, f"Missed reminder: {message}", delay=4.0 + count)
        else:
            _schedule(rid, due, message)
        count += 1
    return count


def set_timer(seconds: int, message: str = "Timer finished") -> dict:
    """Set a one-off timer that announces `message` after `seconds`."""
    if seconds <= 0:
        return {"error": "seconds must be a positive number."}
    due = time.time() + seconds
    item = store.add("reminders", due=due, message=message)
    _schedule(item["id"], due, message)
    return {"status": "scheduled", "id": item["id"], "seconds": seconds, "message": message}


def set_reminder_at(at: str, message: str = "Reminder") -> dict:
    """Set a reminder for a clock time: 'YYYY-MM-DD HH:MM' (24-hour, local
    time) or just 'HH:MM' (today, or tomorrow if that time has passed)."""
    text = (at or "").strip()
    now = datetime.now()
    due = None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            due = datetime.strptime(text, fmt)
            break
        except ValueError:
            pass
    if due is None:
        try:
            clock = datetime.strptime(text, "%H:%M")
            due = now.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
            if due <= now:
                due += timedelta(days=1)
        except ValueError:
            return {"error": "Use 'YYYY-MM-DD HH:MM' or 'HH:MM' (24-hour clock)."}
    if due <= now:
        return {"error": "That time has already passed."}
    result = set_timer(int((due - now).total_seconds()), message)
    result["at"] = due.strftime("%A %d %B, %H:%M")
    return result


def cancel_timer(reminder_id: int) -> dict:
    _meta.pop(reminder_id, None)
    store.remove("reminders", reminder_id)
    t = _active_timers.pop(reminder_id, None)
    if t is None:
        return {"error": f"No active timer with id {reminder_id}."}
    t.cancel()
    return {"status": "cancelled", "id": reminder_id}


def list_timers() -> dict:
    """Pending timers/reminders, soonest first, with when they fire."""
    now = time.time()
    items = [
        {"id": rid, "message": msg,
         "at": datetime.fromtimestamp(due).strftime("%a %d %b %H:%M"),
         "minutes_left": max(0, round((due - now) / 60, 1))}
        for rid, (due, msg) in sorted(_meta.items(), key=lambda kv: kv[1][0])
    ]
    return {"timers": items}
