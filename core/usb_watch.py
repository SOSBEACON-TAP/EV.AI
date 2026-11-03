"""
core/usb_watch.py
-----------------
Notices when a USB drive is plugged in to THIS computer (while EV AI is running) and calls
back with its drive letter and label. Drives that were already there at start-up are ignored.
Plain polling, no admin rights, no extra packages beyond psutil.
"""

import os
import threading
import time


def removable_drives() -> dict[str, str]:
    """{'E:\\\\': 'MY USB'} for every removable drive that is currently plugged in."""
    out: dict[str, str] = {}
    try:
        import psutil
        for part in psutil.disk_partitions(all=False):
            if "removable" in (part.opts or "").lower() or _is_removable(part.mountpoint):
                out[part.mountpoint] = _label(part.mountpoint)
    except Exception:
        pass
    return out


def _is_removable(path: str) -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(path) == 2     # DRIVE_REMOVABLE
    except Exception:
        return False


def is_on_removable_drive(path) -> bool:
    """True if `path` (a file or folder) lives on a removable drive, e.g. EV AI running from a USB stick."""
    try:
        drive = os.path.splitdrive(str(path))[0] + "\\\\"
        return _is_removable(drive)
    except Exception:
        return False


def _label(mountpoint: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(261)
        ctypes.windll.kernel32.GetVolumeInformationW(mountpoint, buf, 261, None, None, None, None, 0)
        return buf.value
    except Exception:
        return ""


class UsbWatcher:
    def __init__(self, on_inserted, interval: float = 3.0, lister=removable_drives):
        self._on_inserted = on_inserted
        self._interval = interval
        self._lister = lister
        self._stop = threading.Event()
        self._known: dict[str, str] = {}

    def start(self) -> None:
        self._known = dict(self._lister())
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self) -> None:
        now = self._lister()
        for drive, label in now.items():
            if drive not in self._known:
                try:
                    self._on_inserted(drive, label)
                except Exception:
                    pass
        self._known = dict(now)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self.poll_once()
