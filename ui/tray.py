"""
ui/tray.py
------------
Optional "minimize to tray": when on (Settings -> Behaviour), closing the
dashboard window hides it to a system-tray icon instead of quitting, so
EV.AI keeps running in the background (wake word, scheduled tasks,
reminders). Right-click the tray icon for Show / Quit; double-click shows
the dashboard. There's no icon file in the project, so the icon is drawn
here.
"""

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config import settings


def _make_icon() -> QIcon:
    from config import APP_ROOT
    path = APP_ROOT / "assets" / "icons" / "ev.ico"
    if path.exists():
        return QIcon(str(path))
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(10, 18, 28))
        painter.setPen(QColor(95, 208, 232))
        painter.drawEllipse(3, 3, 58, 58)
        painter.setPen(QColor(232, 246, 252))
        font = QFont("Segoe UI", 20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "EV")
    finally:
        painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._tray = None
        self._quitting = False
        self._told_user = False

    def set_enabled(self, enabled: bool) -> bool:
        """Returns False if the system has no tray to use."""
        app = QApplication.instance()
        if not enabled:
            if self._tray is not None:
                self._tray.hide()
            app.setQuitOnLastWindowClosed(True)
            return True
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        if self._tray is None:
            self._tray = QSystemTrayIcon(_make_icon(), self)
            self._tray.setToolTip(settings.APP_NAME)
            menu = QMenu()
            menu.addAction("Show").triggered.connect(self.show_window)
            menu.addAction("Release camera").triggered.connect(self.release_camera)
            menu.addSeparator()
            menu.addAction("Quit").triggered.connect(self.quit_app)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(
                lambda reason: self.show_window() if reason == QSystemTrayIcon.DoubleClick else None
            )
            self._menu = menu  # keep alive
        self._tray.show()
        app.setQuitOnLastWindowClosed(False)
        return True

    def is_active(self) -> bool:
        return self._tray is not None and self._tray.isVisible()

    def should_hide_on_close(self) -> bool:
        return self._tray is not None and self._tray.isVisible() and not self._quitting

    def notify_hidden(self) -> None:
        if self._tray is not None and not self._told_user:
            self._told_user = True
            self._tray.showMessage(
                settings.APP_NAME, "Still running in the tray. Right-click the icon to quit.",
                QSystemTrayIcon.Information, 3000,
            )

    def allow_close(self) -> None:
        self._quitting = True

    def show_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def release_camera(self) -> None:
        """Stop Video mode so other apps (e.g. the Windows Camera app) can use the webcam."""
        try:
            freed = self._window.release_camera()
        except Exception:
            freed = False
        if self._tray is not None:
            self._tray.showMessage(
                settings.APP_NAME,
                "Camera released." if freed else "EV AI wasn't using the camera.",
                QSystemTrayIcon.Information, 2500,
            )

    def quit_app(self) -> None:
        self._quitting = True
        self._window.close()
        QApplication.instance().quit()
