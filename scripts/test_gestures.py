"""Offline test of the gesture rules (no camera needed):  python scripts/test_gestures.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.gesture_engine import GestureEngine  # noqa: E402

EXT = {"palm": [1, 1, 1, 1], "fist": [0, 0, 0, 0], "one": [1, 0, 0, 0],
       "two": [1, 1, 0, 0], "three": [1, 1, 1, 0]}


def hand(cx, cy, pose="palm"):
    """21 fake landmarks; palm centre at (cx, cy), fingers pointing up."""
    pts = [(cx, cy)] * 21
    pts = list(pts)
    wrist = (cx, cy + 0.08)
    pts[0] = wrist
    pts[9] = (cx, cy - 0.08)
    for i, (tip, pip) in enumerate(((8, 6), (12, 10), (16, 14), (20, 18))):
        x = cx + (i - 1.5) * 0.02
        pts[pip] = (x, wrist[1] - 0.20)
        pts[tip] = (x, wrist[1] - (0.30 if EXT[pose][i] else 0.12))
    return pts


def run(frames, cfg=None):
    eng = GestureEngine(cfg)
    got, t = [], 1000.0
    for hands in frames:
        t += 1 / 30
        got += [e["action"] for e in eng.update(hands, t)]
    return got, eng


def seconds(n):
    return int(n * 30)


def sweep(x0, x1, y0, y1, n=12, pose="palm"):
    return [[hand(x0 + (x1 - x0) * i / (n - 1), y0 + (y1 - y0) * i / (n - 1), pose)] for i in range(n)]


def two(gap0, gap1, mid0=0.5, mid1=0.5, n=12):
    out = []
    for i in range(n):
        f = i / (n - 1)
        g, m = gap0 + (gap1 - gap0) * f, mid0 + (mid1 - mid0) * f
        out.append([hand(m - g / 2, 0.5), hand(m + g / 2, 0.5)])
    return out


def still(pose, secs, x=0.5, y=0.5):
    return [[hand(x, y, pose)]] * seconds(secs)


checks = [
    ("1 hands toward each other -> zoom_in", two(0.5, 0.2), "zoom_in"),
    ("2 hands apart -> zoom_out", two(0.2, 0.5), "zoom_out"),
    ("3 swipe left -> tab_next", sweep(0.75, 0.35, 0.5, 0.5), "tab_next"),
    ("4 swipe right -> tab_prev", sweep(0.35, 0.75, 0.5, 0.5), "tab_prev"),
    ("5 both left -> desktop_next", two(0.3, 0.3, 0.75, 0.35), "desktop_next"),
    ("6 both right -> desktop_prev", two(0.3, 0.3, 0.35, 0.75), "desktop_prev"),
    ("7 palm held -> pause", still("palm", 1.5), "pause"),
    ("8 hand down -> volume_down", sweep(0.5, 0.5, 0.3, 0.7), "volume_down"),
    ("9 hand up -> volume_up", sweep(0.5, 0.5, 0.7, 0.3), "volume_up"),
    ("10a 1 finger -> app_1", still("one", 1.2), "app_1"),
    ("10b 2 fingers -> app_2", still("two", 1.2), "app_2"),
    ("10c 3 fingers -> app_3", still("three", 1.2), "app_3"),
]
bad = 0
for name, frames, expect in checks:
    got, _ = run(frames)
    ok = expect in got and set(got) <= {expect}
    bad += not ok
    print(("PASS " if ok else "FAIL ") + name, "" if ok else f"(got {got})")

# jitter / idle must do nothing
got, _ = run([[hand(0.5 + 0.004 * (i % 3), 0.5, "fist")] for i in range(90)])
print("PASS idle fist does nothing" if not got else f"FAIL idle: {got}"); bad += bool(got)

# pause then resume with fist; while paused swipes are ignored
frames = still("palm", 1.5) + sweep(0.75, 0.35, 0.5, 0.5) + still("fist", 2.0)
got, eng = run(frames)
ok = got == ["pause", "resume"]
print("PASS pause ignores swipe, fist resumes" if ok else f"FAIL pause/resume: {got}"); bad += not ok

# palm resume mode needs the palm lowered first
frames = still("palm", 1.5) + [[hand(.5, .5, "fist")]] * 10 + still("palm", 2.0)
got, _ = run(frames, {"gesture_resume_mode": "palm"})
ok = got == ["pause", "resume"]
print("PASS palm resume mode" if ok else f"FAIL palm resume: {got}"); bad += not ok

# swipe is not mistaken for pause; slow drift is not a swipe
got, _ = run(sweep(0.6, 0.45, 0.5, 0.5, n=60, pose="fist"))
print("PASS slow drift is not a swipe" if not got else f"FAIL drift: {got}"); bad += bool(got)

# repeating a swipe: left, hand returns, left again -> two tab_next, no tab_prev
frames = (sweep(0.75, 0.35, 0.5, 0.5) + sweep(0.35, 0.75, 0.5, 0.5, n=10)
          + sweep(0.75, 0.35, 0.5, 0.5))
got, _ = run(frames)
ok = got == ["tab_next", "tab_next"]
print("PASS repeated swipe works, return stroke ignored" if ok else f"FAIL repeat swipe: {got}"); bad += not ok

# repeating volume up
frames = sweep(0.5, 0.5, 0.7, 0.3) + sweep(0.5, 0.5, 0.3, 0.7, n=10) + sweep(0.5, 0.5, 0.7, 0.3)
got, _ = run(frames)
ok = got == ["volume_up", "volume_up"]
print("PASS repeated volume up works" if ok else f"FAIL repeat volume: {got}"); bad += not ok

# disabled
got, _ = run(sweep(0.75, 0.35, 0.5, 0.5), {"gestures_enabled": False})
print("PASS disabled does nothing" if not got else f"FAIL disabled: {got}"); bad += bool(got)

print("\nAll good" if not bad else f"\n{bad} FAILED")
sys.exit(1 if bad else 0)
