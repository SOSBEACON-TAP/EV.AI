import sys, tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import secstore as ss

tmp = Path(tempfile.mkdtemp())
ss._dir = lambda: tmp

assert "No scans" in ss.trend_text()
ss.record_score(70, 1, 2); ss.record_score(82, 0, 2)
t = ss.trend_text()
assert "82/100" in t and "up 12" in t and "70, 82" in t, t
ss.record_score(60, 1, 3)
assert "down 22" in ss.trend_text()
for i in range(70): ss.record_score(i, 0, 0)
assert len(ss._load("security_history.json", [])) == 60

devs = [{"ip": "192.168.1.5", "mac": "AA-BB-CC-DD-EE-01", "name": "tv"}, {"ip": "192.168.1.6", "mac": "?", "name": "x"}]
fresh, first = ss.new_devices(devs)
assert first and fresh == []                       # baseline: no alarms
fresh, first = ss.new_devices(devs + [{"ip": "192.168.1.9", "mac": "aa:bb:cc:dd:ee:09", "name": "?"}])
assert not first and [d["ip"] for d in fresh] == ["192.168.1.9"]
fresh, _ = ss.new_devices(devs + [{"ip": "192.168.1.9", "mac": "aa:bb:cc:dd:ee:09", "name": "?"}])
assert fresh == []                                  # only flagged once

f = ss.fixes_for(["Firewall Public: OFF", "Last Windows update installed 90 days ago", "Camera used by: x", "Firewall Private: OFF"])
assert [a for a, _ in f] == ["Open Firewall settings", "Open Windows Update", "Open Camera privacy"], f

# Karen weekly report + allow-list
from datetime import date
from core.karen import Karen
from core import browser_bridge as bb
k = Karen(tmp / "karen.json")
today = date(2026, 11, 7)
k.data["usage"] = {"2026-11-07": {"total": 5400, "apps": {"chrome.exe": 3600, "game.exe": 1800}},
                   "2026-11-05": {"total": 1200, "apps": {"chrome.exe": 1200}}}
rep = k.weekly_report(today)
assert "Week total: 110 min" in rep and "Busiest day: 2026-11-07 (90 min)" in rep and "chrome.exe" in rep, rep
f = k.write_weekly_report(tmp / "rep", today)
assert f.name == "week-2026-11-07.txt" and f.read_text(encoding="utf-8").startswith("KAREN MODE weekly report")
assert "No usage recorded" in Karen(tmp / "empty.json").weekly_report(today)
k.set_rules(60, False, "21:00", "07:00", [], [], True, ["Wikipedia.org", "bad domain!", "khanacademy.org"])
assert k.data["allow_only"] and k.data["allowed_sites"] == ["wikipedia.org", "khanacademy.org"], k.data["allowed_sites"]
k.set_rules(60, False, "21:00", "07:00", [], [])             # old calls keep the allow-list
assert k.data["allow_only"]
b = bb.Bridge(store=tmp / "b.json")
b.set_allow_list(True, ["Wikipedia.org", "x", "javascript:alert(1)"])
assert b.allow_only and b.allowed_sites == ["wikipedia.org"]

# Game profiles + stats
from core import gamestats as gs
gs._dir = lambda: tmp
assert gs.save_profile("  Minecraft   farm ", "Left mouse button", 99, True, 5)
p = gs.profiles()["Minecraft farm"]
assert p == {"target": "Left mouse button", "cps": 50, "break_on": True, "break_min": 10}, p
assert not gs.save_profile("   ", "x", 1, True, 45)
gs.delete_profile("Minecraft farm"); assert gs.profiles() == {}
gs.record_session(10, 5, 0, today)                  # too short: ignored
gs.record_session(3600, 100, 1, today); gs.record_session(1800, 0, 0, today)
sm = gs.summary(7, today)
assert "Total 1 h 30 min in 2 session(s), 1 break reminder(s), 100 auto-clicks." in sm and "2026-11-07    90 min" in sm, sm
assert "No sessions yet" in (gs.summary(7, date(2030, 1, 1)))
print("ideas tests OK")

# --- everyday helpers (dice, converter, stopwatch, countdown) ---
import core.offline as _off
_o = _off.OfflineAssistant.__new__(_off.OfflineAssistant)
assert _o._fun_tools("convert 5 km to miles", "") .startswith("5 km is 3.107")
assert "37.8" in _o._fun_tools("100 f to c", "")
assert "can't be converted" in _o._fun_tools("5 km to kg", "")
assert _o._fun_tools("flip a coin", "") in ("Heads.", "Tails.")
assert _o._fun_tools("roll 3 dice", "").count(",") == 2
assert 5 <= int(_o._fun_tools("pick a number between 9 and 5", "")) <= 9
assert "started" in _o._fun_tools("start stopwatch", "") and "Stopwatch:" in _o._fun_tools("stop stopwatch", "")
assert _o._fun_tools("open youtube", "") is None and _o._fun_tools("2 + 2", "") is None
print("everyday helpers OK")
