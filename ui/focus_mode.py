"""
ui/focus_mode.py
------------------
Focus Mode's distraction blocker. While it runs, EV looks every second or so at
the window in front of you (title + program name only). If it is a browser tab
on a blocked site, or a blocked desktop app (Discord, Scratch ...), EV closes it
(or just warns you, per Settings) and tells you. The matching rules live in
core/focus_match.py.
"""

import time

from PySide6.QtCore import QObject, QTimer, Signal

from core.focus_match import active_window, decide, parse_blocked


class FocusMode(QObject):
    blocked = Signal(str, bool)      # site/app name, was_closed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._blocked: list[str] = []
        self._close = True
        self._last_action = 0.0

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def start(self, blocked_text: str, action: str = "close") -> None:
        self._blocked = parse_blocked(blocked_text)
        self._close = action != "warn"
        self._timer.start(1000)
        print(f"[EV AI] Focus Mode on. Blocking: {self._blocked} ({'close' if self._close else 'warn'})")

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        if not self._blocked or time.time() - self._last_action < 3.0:
            return
        info = active_window()
        if info is None:
            return
        hwnd, title, program = info
        verdict = decide(title, program, self._blocked)
        if verdict is None:
            return
        kind, site = verdict
        self._last_action = time.time()
        closed = False
        if self._close:
            try:
                if kind == "tab":
                    import pyautogui
                    pyautogui.hotkey("ctrl", "w")
                else:
                    import ctypes
                    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE: asks the app to close
                closed = True
            except Exception as e:  # noqa: BLE001
                print(f"[EV AI] Focus Mode couldn't close {site}: {e}")
        print(f"[EV AI] Focus Mode: {kind} '{site}' ({program}) -> {'closed' if closed else 'warned'}")
        self.blocked.emit(site, closed)
