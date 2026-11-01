"""
core/autostart.py
-----------------
"Start with Windows": adds or removes EV AI from the current user's startup list
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run). No admin rights needed.
"""

import sys
from pathlib import Path

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "EV AI"


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    root = Path(__file__).resolve().parent.parent
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    return f'"{exe}" "{root / "main.py"}"'


def is_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
            winreg.QueryValueEx(key, _NAME)
            return True
    except Exception:
        return False


def set_enabled(on: bool) -> tuple[bool, str]:
    try:
        import winreg
    except ImportError:
        return False, "Start with Windows only works on Windows."
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, _NAME)
                except FileNotFoundError:
                    pass
        return True, "EV AI will start with Windows." if on else "EV AI will no longer start with Windows."
    except OSError as e:
        return False, f"Couldn't change the startup setting: {e}"
