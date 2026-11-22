"""Checks Trust Levels, Thought Stream, Action Replay and Self-Evolving Shortcuts without touching real data."""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import habits, replay, thoughts, trust, user_prefs

tmp = Path(tempfile.mkdtemp())
replay._PATH = tmp / "replay.json"
habits._PATH = tmp / "habits.json"
user_prefs._path = lambda: tmp / "prefs.json"

# trust levels
assert trust.level() == "balanced"
f = lambda text="": None
assert trust.needs_ok("type_text", {"text": "x"}, f)
assert not trust.needs_ok("type_text", {"text": "x", "confirmed": True}, f)
assert not trust.needs_ok("create_folder", {}, f)            # balanced: small changes do not ask
trust.set_level("careful")
assert trust.needs_ok("create_folder", {}, f)
assert not trust.needs_ok("get_datetime", {}, f)
trust.set_level("trusting")
assert not trust.needs_ok("type_text", {}, f)
assert not trust.needs_ok("send_email", {}, lambda confirmed=False: None)
trust.set_level("balanced")
assert "type" in trust.intent("type_text", {"text": "hello"})

# replay: steps close together form one run; sends are skipped
replay.record("open_application", {"app_name": "chrome"}, True)
replay.record("open_website", {"target": "gmail"}, True)
replay.record("get_datetime", {}, True)                       # look-ups are not recorded
replay.record("send_email", {"to": "a"}, True)
rs = replay.runs()
assert len(rs) == 1 and [s["tool"] for s in rs[0]] == ["open_application", "open_website", "send_email"], rs

class R:
    def __init__(self): self.calls = []
    def get(self, n): return object()
    def execute(self, n, a): self.calls.append(n); return {"status": "ok"}
r = R()
lines = replay.replay(r, rs[0])
assert r.calls == ["open_application", "open_website"] and "skipped send_email" in lines[2], (r.calls, lines)

# habits: the same pair three times becomes a suggestion
for _ in range(3):
    habits._state["prev"] = None
    habits.record("open_application", {"app_name": "chrome"}, True)
    habits.record("open_website", {"target": "gmail"}, True)
sg = habits.suggestions()
assert any(len(s["steps"]) == 2 for s in sg), sg
sid = sg[0]["id"]
habits.dismiss(sid)
assert all(s["id"] != sid for s in habits.suggestions())

thoughts.add("note", "hi")
assert thoughts.recent(1)[0]["text"] == "hi"
print("brain features OK")
