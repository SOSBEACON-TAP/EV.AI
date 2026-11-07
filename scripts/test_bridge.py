import json, os, sys, tempfile, threading, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from core.browser_bridge import Bridge, clean_command

got = []
counted = []
b = Bridge(lambda q, page: f"ANS[{q}|{page.get('title')}]", got.append, port=47699, store=Path(tempfile.mkdtemp()) / "t.json", count_fn=lambda s_, n: counted.append((s_, n)) or len(counted))
assert b.start()
B = "http://127.0.0.1:47699"

def call(path, data=None, token="", origin="chrome-extension://abc", host=None):
    req = urllib.request.Request(B + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"X-EV-Token": token, "Content-Type": "application/json", "Origin": origin} if origin else {"X-EV-Token": token})
    if host: req.add_header("Host", host)
    try:
        return 200, json.loads(urllib.request.urlopen(req, timeout=25).read())
    except urllib.error.HTTPError as e:
        return e.code, {}

assert call("/ping")[0] == 200
assert call("/ping", origin="https://evil.example")[0] == 403          # web pages are refused
assert call("/ping", host="evil.example")[0] == 403                    # DNS-rebinding style host refused
assert call("/poll")[0] == 401 and call("/ask", {"question": "x"})[0] == 401
# pairing
code = b.code
bad = "000000" if code != "000000" else "111111"
assert call("/pair", {"code": bad})[0] == 403
st, d = call("/pair", {"code": code}); assert st == 200 and d["token"]; tok = d["token"]
assert call("/pair", {"code": code})[0] == 403                          # a code works once
# lockout after 5 wrong codes
for _ in range(5): call("/pair", {"code": "999999" if b.code != "999999" else "888888"})
assert call("/pair", {"code": b.code})[0] == 403
# ask from popup
st, d = call("/ask", {"question": "hi", "page": {"title": "T", "text": "x"}}, tok); assert d["answer"] == "ANS[hi|T]", d
st, d = call("/count", {"site": "youtube", "n": 2}, tok); assert d == {"today": 1} and counted == [("youtube", 2)], (d, counted)
assert call("/count", {"site": "youtube", "n": 999}, tok)[0] == 400
assert call("/count", {"site": "youtube", "n": 1})[0] == 401
b.set_blocked_sites(["YouTube.com", "bad site", "evil/x", "tiktok.com"])
st, d = call("/rules", token=tok); assert d == {"blocked_sites": ["youtube.com", "tiktok.com"], "allow_only": False, "allowed_sites": []}, d
assert call("/rules")[0] == 401
# commands + poll
assert b.send({"action": "scroll", "dir": "down"})
st, d = call("/poll", token=tok); assert d["command"] == {"action": "scroll", "dir": "down"}, d
assert b.connected
# safety of commands
assert clean_command({"action": "open_url", "url": "javascript:alert(1)"}) is None
assert clean_command({"action": "open_url", "url": "file:///c:/x"}) is None
assert clean_command({"action": "open_url", "url": "example.com"})["url"] == "https://example.com"
assert clean_command({"action": "search", "query": "cats & dogs"})["url"].endswith("cats+%26+dogs")
assert clean_command({"action": "format_disk"}) is None and clean_command({"action": "scroll", "dir": "sideways"}) is None
# voice question round trip
b.ask_about_page("What is this page about?")
st, d = call("/poll", token=tok); assert d["command"]["action"] == "page_text"
call("/page", {"page": {"title": "Home", "text": "hello"}}, tok)
for _ in range(50):
    if got: break
    time.sleep(0.1)
assert got == ["ANS[What is this page about?|Home]"], got
# tokens persist; unpair
assert Bridge(port=47698, store=b._store_path).authorized(tok)
b.forget_all(); assert call("/poll", token=tok)[0] == 401
b.stop()
print("bridge tests OK")
