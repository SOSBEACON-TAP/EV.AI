"""
core/native_host.py
-------------------
Lets the EV AI Chrome extension start EV AI quietly (hidden in the tray) when it is not running.

How: Chrome "native messaging". EV AI registers a small helper entry for the current Windows user
(HKCU, no administrator needed) that points at EV_AI.exe. When the extension asks, Chrome starts
EV_AI.exe with a "chrome-extension://..." argument; main.py sees it, starts the real app in the
background and exits. Only THIS extension (fixed ID) is allowed to do that.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOST_NAME = "com.sosbeacon.evai"
EXTENSION_ID = "pppajnapnggfbmfaoogkfbogmpaagdml"      # fixed by the "key" in chrome_extension/manifest.json
REG_PATHS = (r"Software\Google\Chrome\NativeMessagingHosts", r"Software\Chromium\NativeMessagingHosts")


def is_launch_arg(arg: str) -> bool:
    """Chrome starts a native host with the calling extension's origin as the first argument."""
    return arg.startswith("chrome-extension://")


def manifest(exe: Path) -> dict:
    return {
        "name": HOST_NAME,
        "description": "Starts EV AI quietly when the EV AI Chrome extension needs it",
        "path": str(exe),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }


def register(app_root: Path, exe: Path | None = None) -> bool:
    """Writes the host file and the per-user registry entries. Only for the installed (frozen) app on Windows."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    try:
        import winreg
        exe = exe or Path(sys.executable)
        target = app_root / "data" / f"{HOST_NAME}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(manifest(exe), indent=2)
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
        for base in REG_PATHS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{base}\\{HOST_NAME}") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(target))
        return True
    except Exception as e:
        print(f"[EV AI] Chrome quiet start not registered: {e}")
        return False


def unregister() -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg
        for base in REG_PATHS:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{base}\\{HOST_NAME}")
            except OSError:
                pass
    except Exception:
        pass


def launch_background(exe: Path | None = None) -> None:
    """Called inside the short-lived helper process: starts EV AI hidden and detached, because Chrome
    ends the helper (and anything attached to it) when the extension disconnects."""
    from core import browser_bridge
    exe = exe or Path(sys.executable)
    if _already_running(browser_bridge.HOST, browser_bridge.PORT):
        return
    cmd = [str(exe), "--background"] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"), "--background"]
    flags = 0x00000008 | 0x00000200            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(cmd, creationflags=flags | 0x01000000, close_fds=True)     # + CREATE_BREAKAWAY_FROM_JOB
    except OSError:
        subprocess.Popen(cmd, creationflags=flags, close_fds=True)


def _already_running(host: str, port: int) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False
