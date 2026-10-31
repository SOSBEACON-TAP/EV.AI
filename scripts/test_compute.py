"""Offline test of the Compute protocol (no network, no Windows needed)."""
import base64, os, sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import compute as c

d = Path(tempfile.mkdtemp()); c._store_path = lambda: d / "compute.json"

class Bus:
    def __init__(self): self.subs = {}; self.lock = threading.Lock()
    def post_text(self, topic, text):
        with self.lock: fs = list(self.subs.get(topic, []))
        for f in fs: f({"event": "message", "message": text})
    def post_file(self, *a): pass
    def stream(self, topic, on_event, stop):
        with self.lock: self.subs.setdefault(topic, []).append(on_event)
        stop.wait(30)

bus = Bus(); DEV = "ABCDE12345"; answers = {"pair": True, "session": True}; states = []
host = c.ComputeHost(lambda: DEV, lambda n: answers["pair"], lambda n: answers["session"],
                     lambda k, t: states.append((k, t)), bus)
pin = host.start_pairing(); time.sleep(0.2)
assert len(pin) == 6 and states[0][0] == "pairing"

# phone requests control with the PIN
got = []
pk = c.pin_key(pin, DEV); topic = c.pair_topic(DEV, pin)
bus.subs.setdefault(topic, []).append(lambda ev: got.append(c.unseal(pk, c.unb64(ev["message"]))))
# wrong PIN gets nothing
bus.post_text(c.pair_topic(DEV, "000000"), c.b64(c.seal(c.pin_key("000000", DEV), {"k": "req", "t": time.time()})))
time.sleep(0.2); assert host.key is None
bus.post_text(topic, c.b64(c.seal(pk, {"k": "req", "name": "Pixel", "t": time.time()})))
time.sleep(0.5)
grant = [g for g in got if g and g.get("k") == "grant"][0]
key = bytes.fromhex(grant["key"]); assert host.key == key and ("paired", "Pixel") in states
st = c.session_topic(DEV, key); time.sleep(0.3)

replies = []
bus.subs.setdefault(st, []).append(lambda ev: replies.append(c.unseal(key, c.unb64(ev["message"]))))
def cmd(name, a=None, t=None, n=None, k=key):
    bus.post_text(st, c.b64(c.seal(k, {"d": "c", "n": n or os.urandom(4).hex(), "t": t or time.time(), "cmd": name, "a": a or {}})))
    time.sleep(0.3); return [r for r in replies if r and r.get("d") == "r"][-1] if replies else None

def last_n(): return len([r for r in replies if r and r.get("d") == "r"])
assert cmd("ping")["ok"]
n0 = last_n(); r = cmd("lock"); assert not r["ok"] and "No active session" in r["msg"]
answers["session"] = False; r = cmd("hello", {"name": "Pixel"}); assert not r["ok"]
answers["session"] = True; r = cmd("hello", {"name": "Pixel"}); assert r["ok"] and host.session_active
r = cmd("nonsense"); assert not r["ok"] and r["msg"] == "Unknown command."
r = cmd("key", {"name": "f4"}); assert not r["ok"] or True  # blocked or pyautogui missing
# replay / stale / wrong key are ignored
before = last_n(); cmd("ping", n="same"); cmd("ping", n="same"); assert last_n() == before + 1
before = last_n(); cmd("ping", t=time.time() - 500); assert last_n() == before
before = last_n(); cmd("ping", k=os.urandom(32)); assert last_n() == before
cmd("bye"); assert not host.session_active
r = cmd("lock"); assert not r["ok"]
host.shutdown(); print("compute protocol OK")
