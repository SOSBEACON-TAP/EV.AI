import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import cloud as c

key = c.derive_key("A@x.com", "secret-pass")
assert key == c.derive_key(" a@X.com ", "secret-pass") and key != c.derive_key("a@x.com", "other") and len(key) == 32
blob = c.encrypt(key, {"hello": "wörld"})
assert blob.startswith("v1:") and "wörld" not in blob and c.decrypt(key, blob) == {"hello": "wörld"}
try: c.decrypt(c.derive_key("a@x.com", "bad"), blob); raise SystemExit("decrypt with wrong key must fail")
except Exception as e: assert not isinstance(e, SystemExit)
assert c.merge_lines(["a", "b"], ["b", "c"]) == ["a", "b", "c"] and len(c.merge_lines([str(i) for i in range(100)], [])) == 60
m = c.merge_memories([{"category": "fact", "key": "pet", "value": "old", "created_at": "2026-01-01"}],
                     [{"category": "fact", "key": "pet", "value": "new", "created_at": "2026-02-01"}, {"category": "fact", "key": "city", "value": "x", "created_at": "1"}])
assert {x["value"] for x in m} == {"new", "x"}
assert not any(k in c.SYNC_PREFS for k in ("device_id", "device_server", "home_lat", "home_lon", "home_name", "start_menu_target", "chrome_bridge"))

# a fake server
tmp = Path(tempfile.mkdtemp()); store = {}
def http(method, url, headers, body, timeout=15):
    assert headers["apikey"] == c.SUPABASE_KEY
    if url.endswith("/auth/v1/signup"):
        return (200, {"user": {"id": "u1"}}) if body["email"] == "new@x.com" else (200, {"access_token": "T", "refresh_token": "R", "expires_in": 3600, "user": {"id": "u1"}})
    if "grant_type=password" in url:
        return (200, {"access_token": "T", "refresh_token": "R", "expires_in": 3600, "user": {"id": "u1"}}) if body["password"] == "goodpass1" else (400, {"error_description": "Invalid login credentials"})
    if "grant_type=refresh_token" in url:
        return (200, {"access_token": "T2", "refresh_token": "R2", "expires_in": 3600})
    if method == "GET" and "user_data" in url:
        assert headers["Authorization"].startswith("Bearer T")
        return (200, [store["row"]] if "row" in store else [])
    if method == "POST" and "user_data" in url:
        assert body["user_id"] == "u1" and "on_conflict=user_id" in url
        store["row"] = {"data": body["data"], "updated_at": body["updated_at"]}
        return 201, None
    if url.endswith("/logout"): return 204, None
    raise AssertionError(url)

cl = c.Cloud(http, tmp / "s.json")
assert not cl.signed_in
ok, msg = cl.sign_up("new@x.com", "goodpass1"); assert ok and "confirm" in msg.lower() and not cl.signed_in
assert not cl.sign_up("bad", "x")[0]
ok, msg = cl.sign_in("a@x.com", "wrongpass"); assert not ok and "Wrong email" in msg
ok, msg = cl.sign_in("a@x.com", "goodpass1"); assert ok and cl.signed_in and cl.email == "a@x.com"
assert json.loads((tmp / "s.json").read_text())["refresh"] == "R"
ok, remote, _ = cl.pull(); assert ok and remote is None
snap = {"prefs": {"theme": "dark"}, "summary": ["x"], "memories": [], "profiles": {}}
assert cl.push(snap)[0] and "theme" not in store["row"]["data"]          # stored encrypted
cl._access = ""                                                           # force a refresh
ok, remote, _ = cl.pull(); assert ok and remote == snap and cl._s["refresh"] == "R2"
cl2 = c.Cloud(http, tmp / "s.json")                                       # a restart keeps you signed in
assert cl2.signed_in and cl2.pull()[1] == snap
cl2.sign_out(); assert not cl2.signed_in and not (tmp / "s.json").exists()
print("cloud tests OK")
