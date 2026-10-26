"""
tools/applications.py
------------------------
Open/close applications using Windows' own app-launching mechanism
(os.startfile) rather than hardcoded install paths, so it works for
whatever the user actually has installed and wherever it's installed.

close_application is the first genuinely "sensitive" tool: closing
something can lose unsaved work, so it requires confirmed=true — see
core/router.py's registration of this tool, and the confirmation policy
in core/brain.py's SYSTEM_PROMPT, which instructs the AI to always ask
the user first.
"""

import os
import sys

import psutil

from tools import memory as memory_tools

# Friendly-name -> exe map for common apps. Anything not listed here is
# still tried directly, in case it's already a valid exe name Windows
# can resolve (e.g. the user just says the exe name itself).
_KNOWN_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "spotify": "spotify.exe",
}


def _resolve_target(app_name: str) -> str:
    return _KNOWN_APPS.get(app_name.strip().lower(), app_name.strip())


def open_application(app_name: str) -> dict:
    """Launch an application by common name, e.g. 'notepad', 'chrome'."""
    if sys.platform != "win32":
        return {"error": "Opening applications is only implemented for Windows right now."}

    target = _resolve_target(app_name)
    try:
        os.startfile(target)
    except OSError as e:
        return {"error": f"Could not open '{app_name}': {e}"}
    try:
        memory_tools.get_store().record_app_open(app_name)
    except Exception:
        pass  # usage tracking is a nicety — the app DID open, so never report a failure over it
    return {"status": "opened", "app": app_name}


def close_application(app_name: str, confirmed: bool = False) -> dict:
    """Close a running application by name. Does nothing unless
    confirmed=true — see module docstring."""
    if not confirmed:
        return {
            "confirmation_required": True,
            "message": f"Closing '{app_name}' may lose unsaved work. Ask the user to confirm first.",
        }
    if sys.platform != "win32":
        return {"error": "Closing applications is only implemented for Windows right now."}

    target_exe = _resolve_target(app_name).lower()
    if not target_exe.endswith(".exe"):
        target_exe += ".exe"

    closed_pids = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info["name"] or "").lower() == target_exe:
                proc.terminate()
                closed_pids.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not closed_pids:
        return {"error": f"No running process found matching '{app_name}'."}
    return {"status": "closed", "app": app_name, "pids": closed_pids}
