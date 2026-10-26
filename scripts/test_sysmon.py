import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core.sysmon import SystemWatch, evaluate
ok = True
def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name); ok = ok and cond
w = SystemWatch()
check("normal readings: no warning", w.update(30, 50, 40, 80, True, 0) == [])
r = []
for i in range(4): r += w.update(95, 50, 40, 80, True, i * 2)
check("CPU spike for 4 ticks: no warning yet", r == [])
check("5th tick: CPU warning", len(w.update(95, 50, 40, 80, True, 8)) == 1)
check("no repeat within cooldown", w.update(95, 50, 40, 80, True, 20) == [])
check("repeat after cooldown", len(w.update(95, 50, 40, 80, True, 700)) == 1)
w = SystemWatch(); w.update(30, 50, 40, 80, True, 0)
check("CPU dips reset the counter", all(w.update(95 if i % 2 else 10, 50, 40, 80, True, i) == [] for i in range(10)))
w = SystemWatch()
check("disk full warns", any("full" in m for m in w.update(10, 10, 95, None, True, 0)))
check("low battery warns only unplugged", len(SystemWatch().update(10, 10, 10, 10, False, 0)) == 1 and SystemWatch().update(10, 10, 10, 10, True, 0) == [])
check("evaluate lists problems", len(evaluate(95, 95, 95, 5, False)) == 4 and evaluate(10, 10, 10, 50, True) == [])
print("\nAll good" if ok else "\nSOME FAILED")
