import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import shell, places, antivirus

assert shell.strip_prefix("> dir") == "dir" and shell.strip_prefix("cmd ipconfig /all") == "ipconfig /all"
assert shell.strip_prefix("scan my computer") is None
for bad in ("del /s /q C:\\x", "rd /s foo", "format d:", "shutdown /s", "reg delete HKCU\\x", "dir & del x", "taskkill /f /im a.exe"):
    assert shell.is_dangerous(bad), bad
for ok in ("dir", "ipconfig /all", "ping 8.8.8.8", "echo hello", "cd ..", "type notes.txt", "systeminfo"):
    assert not shell.is_dangerous(ok), ok
d = tempfile.mkdtemp(); os.mkdir(os.path.join(d, "sub"))
sh = shell.Shell(d)
assert sh.run("echo hi") == "hi"
assert sh.run("cd sub").endswith("sub") and sh.cwd.endswith("sub")
assert sh.run("cd ..") == os.path.realpath(d) and "cannot find" in sh.run("cd nope")
assert "stopped" not in sh.run("echo done")

assert abs(places.distance_m(0, 0, 0, 1) - 111195) < 200
assert round(places.bearing_deg(0, 0, 1, 0)) == 0 and round(places.bearing_deg(0, 0, 0, 1)) == 90
assert places.compass(0) == "N" and places.compass(135) == "SE" and places.nice(450) == "450 m" and places.nice(1500) == "1.5 km"
q = places.build_query(12.9, 77.6, 500); assert "around:500,12.9,77.6" in q
ps = places.parse_places('{"elements":[{"lat":12.91,"lon":77.6,"tags":{"amenity":"pharmacy","name":"MedPlus"}},{"lon":1}]}', 12.9, 77.6)
assert len(ps) == 1 and ps[0]["name"] == "MedPlus" and 1000 < ps[0]["meters"] < 1200 and ps[0]["kind"] == "pharmacy"
ok, msg = antivirus.scan("custom", "")
assert not ok
print("ultron tools OK")
