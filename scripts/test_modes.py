import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, date
from pathlib import Path
from core import gamemode as g, karen as k

# --- game mode
sent = []
c = g.Clicker(sender=lambda kind, arg: sent.append((kind, arg)), corner_check=lambda: False)
assert c.start(20, "left", max_clicks=5); time.sleep(0.6); assert c.count == 5 and sent[0] == ("mouse", "left") and not c.running
sent.clear(); c2 = g.Clicker(sender=lambda kind, arg: sent.append((kind, arg)), corner_check=lambda: False)
assert c2.start(50, "e"); time.sleep(0.2); c2.stop(); assert sent and sent[0] == ("key", ord("E")) and not c2.running
assert not c2.start(10, "nonsense") and "Unknown key" in c2.stopped_reason
c3 = g.Clicker(sender=lambda *a: None, corner_check=lambda: True); c3.start(10, "left"); time.sleep(0.2); assert "corner" in c3.stopped_reason
assert g.vk_for("F6") == 0x75 and g.vk_for("space") == 0x20 and g.vk_for("zz") is None
assert g.parse_scheme_guid("Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)") == g.HIGH_PERFORMANCE
apps = g.filter_apps([(1, "chrome.exe", 500 << 20), (2, "chrome.exe", 300 << 20), (3, "svchost.exe", 900 << 20), (4, "EV_AI.exe", 1 << 30),
                      (5, "slack.exe", 100 << 20), (6, "self.exe", 2 << 30)], own_pid=6)
assert [a["name"] for a in apps] == ["chrome.exe", "slack.exe"] and apps[0]["mb"] == 800 and apps[0]["pids"] == [1, 2]

# --- karen mode
p = Path(tempfile.mkdtemp()) / "k.json"; K = k.Karen(p)
assert not K.set_pin("12") and K.set_pin("2468") and K.has_pin
assert "2468" not in p.read_text()
assert K.check_pin("2468") and not K.check_pin("0000")
for _ in range(5): K.check_pin("1111", now=1000.0)
assert not K.check_pin("2468", now=1001.0) and K.pin_locked_for(now=1001.0) > 200 and K.check_pin("2468", now=1000.0 + 301)
K2 = k.Karen(p); assert K2.has_pin and K2.check_pin("2468")                       # persisted
K.set_rules(60, True, "21:00", "07:00", ["Game.EXE", " "], ["https://www.YouTube.com/x", "bad site", "tiktok.com"])
assert K.data["blocked_apps"] == ["game.exe"] and K.data["blocked_sites"] == ["youtube.com", "tiktok.com"]
mk = lambda h, m=0: datetime(2026, 11, 6, h, m)
assert K.in_bedtime(mk(22)) and K.in_bedtime(mk(3)) and not K.in_bedtime(mk(12)) and not K.in_bedtime(mk(7))
K.set_enabled(True)
assert K.tick(mk(12), "chrome.exe", 0, 5) == [] and K.used_today("2026-11-06") == 5
assert K.tick(mk(12), "chrome.exe", 120, 5) == [] and K.used_today("2026-11-06") == 5          # idle is not counted
K.data["usage"]["2026-11-06"]["total"] = 60 * 60 - 200
a = K.tick(mk(12), "x.exe", 0, 5); assert [x["do"] for x in a] == ["warn"] and "Five" in a[0]["text"]
assert K.tick(mk(12), "x.exe", 0, 5) == []                                                       # warned once
K.data["usage"]["2026-11-06"]["total"] = 60 * 60
a = K.tick(mk(12), "x.exe", 0, 5); assert a and a[0]["do"] == "lock"
assert K.tick(mk(12), "x.exe", 0, 5) == []                                                       # lock is rate-limited
K.grant_minutes(30, "2026-11-06"); assert K.remaining_seconds("2026-11-06") > 1700
K._last_lock = 0; assert K.tick(mk(23), "x", 0, 5)[0]["do"] == "lock"                            # bedtime
a = K.tick(mk(12), "x", 0, 5, running={"game.exe", "other.exe"}); assert any(x["do"] == "kill" and x["name"] == "game.exe" for x in a)
K.set_enabled(False); assert K.tick(mk(23), "x", 0, 5) == []
assert "KAREN" in K.report(today=date(2026, 11, 6)) and "min" in K.report(today=date(2026, 11, 6))
assert "OFF" in K.status_line() and k.clean_sites(["a.com", "A.com", "nodot"]) == ["a.com"]
print("game + karen tests OK")
