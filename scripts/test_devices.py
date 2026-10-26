import pathlib, sys, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core import devices, user_prefs
ok = True
def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name); ok = ok and cond

codes = [devices.new_code() for _ in range(50)]
check("new codes are valid", all(devices.decode_code(c) for c in codes))
check("every phone gets a different code", len(set(codes)) == 50)
c = codes[0]
check("lower case and spaces accepted", devices.decode_code(c.lower().replace("-", " ")) == devices.decode_code(c))
check("without EV- prefix accepted", devices.decode_code(c[3:]) == devices.decode_code(c))
bad = c[:-1] + ("0" if c[-1] != "0" else "1")
check("typo in check char rejected", devices.decode_code(bad) is None)
check("garbage rejected", devices.decode_code("hello") is None and devices.decode_code("") is None)
dev = devices.decode_code(c)
check("topic is private-looking", devices.topic_for(dev) == "ev-" + dev.lower() and len(devices.topic_for(dev)) == 13)
check("mask hides the id", dev[:5] not in devices.mask(dev))
check("shutdown message has the task", "write my essay" in devices.shutdown_message("write   my essay"))

sent = {}
class FakeResp:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): return False
def fake_open(req, timeout=0):
    sent["url"], sent["body"] = req.full_url, req.data.decode()
    sent["h"] = {k.lower(): v for k, v in req.header_items()}
    return FakeResp()
urllib.request.urlopen = fake_open
store = {}
user_prefs.get = lambda k: store.get(k, {"call_on_shutdown": True}.get(k, ""))
user_prefs.set_value = lambda k, v: store.__setitem__(k, v)
check("no device -> no alert", devices.call_for_shutdown("x")[0] is False and not sent)
check("connect with a bad code fails", devices.connect("EV-AAAAA-BBBBB-C")[0] is False)
check("connect with a good code", devices.connect(c)[0] and store["device_id"] == dev)
res = devices.call_for_shutdown("write my essay")
check("alert is sent to the device channel", res[0] and sent["url"] == "https://ntfy.sh/" + devices.topic_for(dev))
check("alert is urgent with the task text", sent["h"]["priority"] == "urgent" and "write my essay" in sent["body"])
store["call_on_shutdown"] = False; sent.clear()
check("switch off -> no alert", devices.call_for_shutdown("x")[0] is False and not sent)
store["call_on_shutdown"] = True; store["device_server"] = "https://my.server/"
devices.call_for_shutdown("x")
check("custom server used", sent["url"].startswith("https://my.server/ev-"))
def boom(req, timeout=0): raise OSError("offline")
urllib.request.urlopen = boom
check("network error is reported, not raised", devices.ring_phone("x")[0] is False)
devices.disconnect()
check("disconnect clears", store["device_id"] == "")
print("\nAll good" if ok else "\nSOME FAILED")
