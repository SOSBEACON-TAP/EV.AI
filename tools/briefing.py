"""
tools/briefing.py
-------------------
"Good morning" briefing: today's date, unread mail (sender/subject only),
pending timers, and recurring scheduled tasks — gathered in one call so
the assistant can read it out as a short spoken summary.
"""

from datetime import datetime

from tools import automation as automation_tools
from tools import mailer, reminders, tasks


def morning_briefing() -> dict:
    now = datetime.now()
    result = {"date": now.strftime("%A, %d %B %Y"), "time": now.strftime("%H:%M")}

    mail = mailer.check_email(unread_only=True, limit=5)
    result["email"] = mail if "error" not in mail else {"unavailable": mail["error"]}

    result["timers"] = reminders.list_timers()["timers"]
    result["todos"] = tasks.list_todos()["todos"]
    try:
        result["scheduled_tasks"] = automation_tools.list_scheduled_tasks()
    except Exception as e:
        result["scheduled_tasks"] = {"unavailable": str(e)}
    return result
