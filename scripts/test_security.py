import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import security as s

r = s.password_report("password"); assert r["rating"] == "VERY WEAK", r
r = s.password_report("k9#Vq2!xLm8@Zp4wQ"); assert r["rating"] in ("STRONG", "EXCELLENT"), r
g = s.generate_password(20); assert len(g) == 20 and s.password_report(g)["rating"] != "VERY WEAK"
a = s.audit_passwords(["abc", "abc", g]); assert any(f["level"] == "bad" for f in a)
assert s.parse_arp("  192.168.1.1  aa-bb-cc-dd-ee-ff  dynamic") == {"192.168.1.1": "aa:bb:cc:dd:ee:ff"}
w = s.parse_wifi("SSID 1 : Home\n    Authentication : WPA2-Personal\n    BSSID 1 : aa\n         Signal : 88%\n         Channel : 6\nSSID 2 : Cafe\n    Authentication : Open\n         Signal : 40%\n         Channel : 1\n")
assert [n["ssid"] for n in w] == ["Home", "Cafe"] and w[0]["signal"] == 88
assert s.wifi_security_level("Open") == "bad" and s.wifi_security_level("WPA2-Personal") == "ok" and s.wifi_security_level("WEP") == "warn"
d = tempfile.mkdtemp()
open(os.path.join(d, "invoice.pdf.exe"), "wb").write(b"MZ" + b"0" * 10)
open(os.path.join(d, "notes.txt"), "w").write("hi")
fr = s.file_report(os.path.join(d, "invoice.pdf.exe")); assert any(f["level"] == "bad" for f in fr), fr
assert any("Disguised" in f["text"] for f in s.scan_folder(d))
for name, fn in s.SIMULATIONS.items():
    out = fn(); assert out and "SIM" in out[0].upper(), name
assert 0 <= s.score([s.F("bad", "x")] * 9) <= 100 and s.score([]) == 100
assert s.analyze_website("")[0]["level"] == "warn"
print("security tests OK")
