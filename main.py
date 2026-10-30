"""
main.py
-------
EV AI entry point.

Startup sequence:
1. Load configuration
2. Show the startup screen (progress bar) and, if FACE_AUTH_ENABLED,
   verify the webcam sees the enrolled owner before continuing -> Stage 10
3. Start UI (MainWindow)
"""

import signal
import sys
from pathlib import Path

# Auto-delete __pycache__ (Settings toggle, on by default): stop Python
# from writing new bytecode caches for the rest of this run, and sweep
# out any that already exist. Must come before the project's other
# imports, which is when the caches would otherwise get written. Never
# allowed to stop EV.AI from starting.
from core import user_prefs as _user_prefs
try:
    if _user_prefs.get("auto_clear_pycache"):
        sys.dont_write_bytecode = True
        from core.pycache_cleaner import clear_pycache as _clear_pycache
        _clear_pycache(Path(__file__).resolve().parent)
except Exception:
    pass

# Installed before any other project module is imported, so even
# import-time prints (pygame's banner, warnings from optional deps,
# etc.) end up in the in-app log that Settings -> View Log shows —
# see core/log_buffer.py.
from core.log_buffer import install as _install_log_capture
_install_log_capture()

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from config import settings
from ui.main_window import MainWindow
from ui.startup_screen import StartupScreen
from ui.theme import apply_theme


def main() -> int:
    warnings = settings.validate()
    for w in warnings:
        print(f"[EV AI] Config warning: {w}")

    # Windows taskbar identity: without this the window is grouped under
    # pythonw.exe and shows the Python logo. Must match
    # scripts/create_shortcut.py so the pinned shortcut and the running
    # window are the same taskbar button.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EV.AI.Assistant")
        except Exception:
            pass

    try:
        from core.shortcuts import ensure_start_menu_entry
        import threading
        threading.Thread(target=ensure_start_menu_entry, daemon=True).start()
    except Exception:
        pass

    try:
        from app_version import BUILD as _build, VERSION as _version
        print(f"[EV AI] version {_version} build {_build}")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName(settings.APP_NAME)
    # Give the app font a real point size: some widgets otherwise ask for a
    # size of -1, which Qt reports as "QFont::setPointSize: Point size <= 0".
    _font = app.font()
    if _font.pointSizeF() <= 0:
        _font.setPointSizeF(9.0)
        app.setFont(_font)
    _icon_path = Path(__file__).resolve().parent / "assets" / "icons" / "ev.ico"
    if _icon_path.exists():
        app.setWindowIcon(QIcon(str(_icon_path)))
    apply_theme(app, _user_prefs.get("theme"))

    # Kept alive via this dict (not a local that falls out of scope) so
    # the MainWindow instance isn't garbage-collected the moment
    # _launch_main_window() returns.
    state = {"window": None}

    def _launch_main_window() -> None:
        window = MainWindow()
        hidden_start = bool(_user_prefs.get("start_in_tray") and window._tray.is_active())
        window.show()
        if hidden_start:
            window.hide()
            window._tray.notify_hidden()
        state["window"] = window
        if hidden_start:
            print("[EV AI] Starting hidden in the tray")
        else:
            window.setWindowOpacity(max(0.6, min(1.0, int(_user_prefs.get("window_opacity")) / 100.0)))

    def _deny_and_quit(reason: str) -> None:
        print(f"[EV AI] Startup blocked by face check: {reason}")
        app.quit()

    splash = StartupScreen()
    splash.start(on_ok=_launch_main_window, on_denied=_deny_and_quit)

    # Make Ctrl+C in the terminal close EV AI cleanly instead of hitting
    # mid-frame inside a Qt paint call (which used to leave a dangling
    # QPainter and spam "QBackingStore::endPaint()" warnings forever).
    # Qt's event loop is mostly C++, so Python only gets a chance to run
    # its signal handler between events — the idle QTimer below forces
    # that chance to come around regularly.
    def _handle_sigint(*_args):
        print("\n[EV AI] Shutting down (Ctrl+C)...")
        app.quit()

    signal.signal(signal.SIGINT, _handle_sigint)
    _sigint_pump = QTimer()
    _sigint_pump.timeout.connect(lambda: None)
    _sigint_pump.start(200)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
