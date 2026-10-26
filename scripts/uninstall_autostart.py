"""
scripts/uninstall_autostart.py
--------------------------------
Removes the launcher installed by scripts/install_autostart.py, so EV AI
stops starting automatically at Windows login.

    venv\\Scripts\\python.exe scripts\\uninstall_autostart.py
"""

import os
import sys
from pathlib import Path

STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LAUNCHER_NAME = "EV_AI_autostart.vbs"


def main() -> int:
    if os.name != "nt":
        print("Autostart setup only applies on Windows.")
        return 1

    launcher_path = STARTUP_DIR / LAUNCHER_NAME
    if not launcher_path.exists():
        print("Autostart isn't currently installed — nothing to do.")
        return 0

    launcher_path.unlink()
    print(f"Removed: {launcher_path}")
    print("EV AI will no longer start automatically at login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
