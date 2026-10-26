"""
ui/hotkey.py
--------------
Global hotkey (Windows): Ctrl+Alt+E shows/hides EV from anywhere, even when
another app has focus. Uses the Win32 RegisterHotKey call plus a Qt native
event filter — no extra packages. If another program already owns the
combination, registration quietly fails and EV simply has no hotkey.
"""

import sys

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication

_MOD_ALT, _MOD_CONTROL, _MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
_VK_E = 0x45
_WM_HOTKEY = 0x0312
_HOTKEY_ID = 0x4556   # "EV"

LABEL = "Ctrl+Alt+E"


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self._registered = False

    def enable(self) -> bool:
        if sys.platform != "win32" or self._registered:
            return self._registered
        try:
            import ctypes
            ok = ctypes.windll.user32.RegisterHotKey(
                None, _HOTKEY_ID, _MOD_CONTROL | _MOD_ALT | _MOD_NOREPEAT, _VK_E)
        except Exception:
            ok = False
        if ok:
            QApplication.instance().installNativeEventFilter(self)
            self._registered = True
        return self._registered

    def disable(self) -> None:
        if not self._registered:
            return
        try:
            import ctypes
            ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
            QApplication.instance().removeNativeEventFilter(self)
        except Exception:
            pass
        self._registered = False

    def nativeEventFilter(self, event_type, message):
        if self._registered and bytes(event_type) == b"windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    self._callback()
                    return True, 0
            except Exception:
                pass
        return False, 0
