"""
ui/usage_tracker.py
---------------------
Feeds core/app_usage.py: every few seconds, notes which program has the front
window and adds the elapsed time to it. Tracks the ACTIVE window (what you are
using), not merely running processes. Skips time when you've been away from the
keyboard/mouse for a couple of minutes, when tracking is switched off in
Settings, and for programs on your exclude list. EV AI's own windows are never
counted.
"""

import sys
import time

from PySide6.QtCore import QObject, QTimer

from core import app_usage, user_prefs
from core.focus_match import active_window

_TICK_MS = 5000
_IDLE_LIMIT_S = 120       # no input for this long -> not counted
_MAX_GAP_S = 15           # longest gap credited per tick (sleep / hang guard)


def idle_seconds() -> float:
    """Seconds since the last key press or mouse move (Windows); 0 elsewhere."""
    if sys.platform != "win32":
        return 0.0
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        return max(0.0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0)
    except Exception:
        return 0.0


class UsageTracker(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._last = time.monotonic()

    def start(self) -> None:
        self._last = time.monotonic()
        self._timer.start(_TICK_MS)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        now = time.monotonic()
        elapsed = min(now - self._last, _MAX_GAP_S)
        self._last = now
        try:
            if not user_prefs.get("usage_tracking") or idle_seconds() > _IDLE_LIMIT_S:
                return
            info = active_window()
            if info is None:
                return
            app_usage.add_time(info[2], elapsed)
        except Exception as e:  # noqa: BLE001
            print(f"[EV AI] Usage tracker skipped a tick: {e}")
