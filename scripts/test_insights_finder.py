"""
Checks App Usage Insights storage and the File Finder's search rules on made-up
data in a temporary folder (your real data and files are not touched):

    venv\\Scripts\\python.exe scripts\\test_insights_finder.py
"""
import os
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import app_usage, file_finder  # noqa: E402

tmp = Path(tempfile.mkdtemp())
app_usage.DB_PATH = tmp / "usage.db"
file_finder.DB_PATH = tmp / "files.db"
bad = 0


def check(name, ok, extra=""):
    global bad
    bad += not ok
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))


# -- usage ---------------------------------------------------------------------
app_usage.add_time("chrome.exe", 3720)
app_usage.add_time("Code.exe", 5400)
app_usage.add_time("Discord.exe", 300)
app_usage.add_time("chrome.exe", 600, date.today() - timedelta(days=2))
s = app_usage.get_usage_summary("today")
check("usage: top app is VS Code", s["top_apps"][0]["app"] == "VS Code", s)
check("usage: total 2h 37m", s["total"] == "2h 37m", s["total"])
check("usage: coding category", app_usage.get_usage_summary("week", "coding")["top_apps"][0]["app"] == "VS Code")
check("usage: 7 daily totals", len(app_usage.daily_totals(7)) == 7)
app_usage.clear_history()
check("usage: cleared", app_usage.app_totals("month") == [])

# -- files ---------------------------------------------------------------------
root = tmp / "home"


def mk(rel, age_days=0.0):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))


mk("Downloads/EV/EV_AI/main.py", 1)
mk("Downloads/EV/EV_AI/ev_ai_notes.py", 3)
mk("Downloads/report.pdf", 2)
mk("Downloads/cat.png", 1)
mk("Documents/Arduino/blink/blink.ino", 5)
mk("Documents/slides/Final Presentation.pptx", 0.2)
mk("Desktop/venv/lib/skipme.py", 0)
file_finder.build_index(20, [root])
file_finder.ensure_index = lambda *a, **k: None


def first(q):
    r = file_finder.search(q)["results"]
    return r[0]["name"] if r else None


check("files: EV AI python file", first("find my EV AI python file") in ("ev_ai_notes.py", "main.py"))
check("files: presentation", first("the presentation I edited recently") == "Final Presentation.pptx")
check("files: images in Downloads", first("show me all images in Downloads") == "cat.png")
check("files: pdf in downloads", first("find PDFs in Downloads") == "report.pdf")
check("files: arduino project folder", first("find my arduino projects") == "blink")
check("files: typo still finds", first("presentaton") == "Final Presentation.pptx")
check("files: venv skipped", first("skipme") is None)
print("\nAll good" if not bad else f"\n{bad} FAILED")
sys.exit(1 if bad else 0)
