import base64, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import native_host as nh

m = json.loads(Path("chrome_extension/manifest.json").read_text())
der = base64.b64decode(m["key"])
eid = "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(der).hexdigest()[:32])
assert eid == nh.EXTENSION_ID, (eid, nh.EXTENSION_ID)
assert "nativeMessaging" in m["permissions"]
mf = nh.manifest(Path(r"C:\EV\EV_AI.exe"))
assert mf["allowed_origins"] == [f"chrome-extension://{eid}/"] and mf["type"] == "stdio"
assert nh.is_launch_arg("chrome-extension://abc/") and not nh.is_launch_arg("--background")
assert nh.register(Path(".")) is False        # not frozen / not Windows here
print("native host tests OK")
