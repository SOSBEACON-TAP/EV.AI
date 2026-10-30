"""
core/shortcuts.py
-------------------
Standalone (.exe) app only: puts "EV AI" in the Windows Start menu, with the EV logo
and the same taskbar identity the running window uses, so it can be pinned to the
taskbar and found like any installed app. Done once per location of EV_AI.exe.
"""

import os
import sys
from pathlib import Path


def ensure_start_menu_entry() -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        from core import user_prefs
        exe = Path(sys.executable).resolve()
        if user_prefs.get("start_menu_target") == str(exe):
            return
        start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if not start_menu.is_dir():
            return
        from scripts.create_shortcut import create_shortcuts
        code, out = create_shortcuts(exe, "", exe.parent, f"{exe},0", [start_menu / "EV AI.lnk"])
        if code == 0:
            user_prefs.set_value("start_menu_target", str(exe))
        else:
            print(f"[EV AI] Couldn't create the Start menu entry: {out}")
    except Exception as e:  # never stop the app over a shortcut
        print(f"[EV AI] Start menu entry skipped: {e}")
