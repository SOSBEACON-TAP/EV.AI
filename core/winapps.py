"""
core/winapps.py
---------------
"Is this app installed on this PC?" checks, so EV never hands Windows a link (like whatsapp://...) that nothing
can open. Windows answers such a link with a "Get an app to open this link" window that sends people to the
Microsoft Store, which is exactly what we do not want. Every check is read-only and failure-safe: when a check
cannot tell, the answer is "no", and callers fall back to the web version.
"""

from __future__ import annotations

import os
import sys

_cache: dict[str, bool] = {}


def _registry_protocol(scheme: str) -> bool:
    """True when some program registered itself as the handler of `scheme://` links (classic installers)."""
    try:
        import winreg
    except ImportError:
        return False
    for hive, path in ((winreg.HKEY_CLASSES_ROOT, scheme),
                       (winreg.HKEY_CURRENT_USER, rf"Software\Classes\{scheme}"),
                       (winreg.HKEY_LOCAL_MACHINE, rf"Software\Classes\{scheme}")):
        try:
            with winreg.OpenKey(hive, path) as k:
                try:
                    winreg.QueryValueEx(k, "URL Protocol")
                    return True
                except OSError:
                    pass
                try:
                    winreg.OpenKey(k, r"shell\open\command").Close()
                    return True
                except OSError:
                    pass
        except OSError:
            continue
    return False


def _registry_has_package(word: str) -> bool:
    """True when a Microsoft Store (packaged) app whose name contains `word` is installed for this PC or this user."""
    try:
        import winreg
    except ImportError:
        return False
    word = word.lower()
    for hive, path in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Applications"),
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages")):
        try:
            with winreg.OpenKey(hive, path) as k:
                i = 0
                while True:
                    try:
                        if word in winreg.EnumKey(k, i).lower():
                            return True
                    except OSError:
                        break
                    i += 1
        except OSError:
            continue
    return False


def _has_files(word: str) -> bool:
    """The 'app execution alias' a Store app leaves in WindowsApps, or the classic installer's own exe."""
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return False
    try:
        if any(word in n.lower() for n in os.listdir(os.path.join(local, "Microsoft", "WindowsApps"))):
            return True
    except OSError:
        pass
    return os.path.exists(os.path.join(local, word, f"{word}.exe"))


def _powershell_has_package(word: str) -> bool:
    import subprocess
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            f"(Get-AppxPackage -Name *{word}* | Select-Object -First 1).Name"],
                           capture_output=True, text=True, timeout=8,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return bool((r.stdout or "").strip())
    except Exception:
        return False


def whatsapp_desktop_installed(refresh: bool = False) -> bool:
    """True when the WhatsApp desktop app (Microsoft Store or classic installer) is on this PC."""
    if not refresh and "whatsapp" in _cache:
        return _cache["whatsapp"]
    found = False
    if sys.platform == "win32":
        found = (_registry_protocol("whatsapp") or _registry_has_package("whatsapp")
                 or _has_files("whatsapp") or _powershell_has_package("whatsapp"))
    _cache["whatsapp"] = found
    return found
