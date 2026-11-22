"""Every user_prefs.get("x") / set_value("x") in the code must name a key that exists in core/user_prefs.DEFAULTS.
A missing key raises KeyError, and when that happens while the main window is being built the app never opens."""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from core import user_prefs

bad = []
for f in root.rglob("*.py"):
    if any(x in f.parts for x in ("venv", ".venv", "site-packages", "build", "dist")):
        continue
    if f.name == "check_prefs_keys.py":
        continue
    for m in re.finditer(r'user_prefs\.(?:get|set_value)\(\s*["\']([A-Za-z0-9_]+)["\']', f.read_text(encoding="utf-8", errors="ignore")):
        if m.group(1) not in user_prefs.DEFAULTS:
            bad.append(f"{f.relative_to(root)}: {m.group(1)}")
if bad:
    print("Missing from DEFAULTS:\n  " + "\n  ".join(sorted(set(bad))))
    sys.exit(1)
print("prefs keys OK")
