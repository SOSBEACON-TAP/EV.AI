"""
scripts/install_autostart.py
-----------------------------
Run this once to make EV AI start automatically whenever you log into
Windows:

    venv\\Scripts\\python.exe scripts\\install_autostart.py

It drops a tiny launcher script into your Windows Startup folder
(shell:startup) — anything there runs automatically at login, no admin
rights or registry edits needed. The launcher uses pythonw.exe (not
python.exe) so no console window flashes up at boot; EV AI's own window
(and, if FACE_AUTH_ENABLED, the startup face check) is all you'll see.

To undo this later, run scripts/uninstall_autostart.py.
"""

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LAUNCHER_NAME = "EV_AI_autostart.vbs"


def _find_pythonw() -> Path:
    """Prefer the venv's pythonw.exe (same folder as the running
    python.exe); fall back to whatever interpreter is running this
    script if no venv pythonw is found."""
    venv_pythonw = PROJECT_DIR / "venv" / "Scripts" / "pythonw.exe"
    if venv_pythonw.exists():
        return venv_pythonw

    candidate = Path(sys.executable).with_name("pythonw.exe")
    if candidate.exists():
        return candidate

    print("[EV AI] Warning: couldn't find pythonw.exe — using python.exe instead, "
          "so a console window will briefly appear at each login.")
    return Path(sys.executable)


def main() -> int:
    if os.name != "nt":
        print("Autostart setup only applies on Windows.")
        return 1

    main_py = PROJECT_DIR / "main.py"
    if not main_py.exists():
        print(f"Couldn't find {main_py} — run this script from inside the EV_AI project.")
        return 1

    pythonw = _find_pythonw()
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    launcher_path = STARTUP_DIR / LAUNCHER_NAME

    # A plain .vbs dropped straight into the Startup folder runs on login
    # with no visible window and no shortcut (.lnk) needed — WshShell.Run's
    # third argument (0) is what hides the window.
    vbs_content = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.CurrentDirectory = "{PROJECT_DIR}"\n'
        f'WshShell.Run """{pythonw}"" ""{main_py}""", 0, False\n'
    )
    launcher_path.write_text(vbs_content, encoding="utf-8")

    print(f"Installed: {launcher_path}")
    print("EV AI will now start automatically the next time you log into Windows.")
    print("(Run scripts/uninstall_autostart.py any time to undo this.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
