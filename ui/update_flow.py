"""
ui/update_flow.py
-------------------
The "Check for updates" experience: look at the update source, tell the user
what's new, and — if they say yes — download, verify and install it (see
core/updater.py), then offer to restart. All network and file work runs on
background threads so the window never freezes.
"""

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox, QPushButton

from config import APP_ROOT, settings
from core import updater, updates


class InfoWorker(QThread):
    info_ready = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            self.info_ready.emit(updater.fetch_info(self._url))
        except updater.UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Unexpected error: {e}")


class InstallWorker(QThread):
    progress = Signal(int)      # percent
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            result = updater.check_and_install(
                self._url, settings.APP_VERSION, APP_ROOT,
                progress=lambda done, total: self.progress.emit(int(done * 100 / total)),
            )
        except updater.UpdateError as e:
            self.failed.emit(str(e))
            return
        except Exception as e:
            self.failed.emit(f"Unexpected error: {e}")
            return
        self.finished_ok.emit(result)


class UpdateFlow(QObject):
    """Drives the interactive check -> confirm -> install -> restart flow
    from a button (Settings -> System & About -> Check for updates)."""

    def __init__(self, parent_widget, button: QPushButton):
        super().__init__(parent_widget)
        self._parent = parent_widget
        self._button = button
        self._label = button.text()
        self._info_worker = None
        self._install_worker = None

    def start(self) -> None:
        url = settings.UPDATE_CHECK_URL
        if not url:
            QMessageBox.information(self._parent, "Check for updates", updates.check("", settings.APP_VERSION)[1])
            return
        self._busy("Checking…")
        self._info_worker = InfoWorker(url, self)
        self._info_worker.info_ready.connect(self._on_info)
        self._info_worker.failed.connect(self._on_failed)
        self._info_worker.start()

    # -- steps -------------------------------------------------------------
    def _busy(self, text: str) -> None:
        self._button.setEnabled(False)
        self._button.setText(text)

    def _idle(self) -> None:
        self._button.setEnabled(True)
        self._button.setText(self._label)

    def _on_failed(self, message: str) -> None:
        self._idle()
        QMessageBox.warning(self._parent, "Check for updates", message)

    def _on_info(self, info: dict) -> None:
        self._idle()
        latest = info["version"]
        if updater.parse_version(latest) <= updater.parse_version(settings.APP_VERSION):
            QMessageBox.information(self._parent, "Check for updates",
                                    f"You're up to date ({settings.APP_VERSION}).")
            return
        notes = f"\n\nWhat's new:\n{info['notes']}" if info["notes"] else ""
        if not info["zip_url"] or not info["sha256"]:
            link = f"\n\nGet it: {info['url']}" if info["url"] else ""
            QMessageBox.information(
                self._parent, "Check for updates",
                f"Version {latest} is available (you have {settings.APP_VERSION}).{notes}{link}\n\n"
                "It can't be installed automatically — copy the new files over your EV.AI folder.")
            return
        answer = QMessageBox.question(
            self._parent, "Update available",
            f"Version {latest} is available (you have {settings.APP_VERSION}).{notes}\n\n"
            "Download and install it now? Your settings, memory and keys are kept, and the "
            "files being replaced are backed up first.",
        )
        if answer != QMessageBox.Yes:
            return
        self._busy("Updating… 0%")
        self._install_worker = InstallWorker(settings.UPDATE_CHECK_URL, self)
        self._install_worker.progress.connect(lambda pct: self._button.setText(f"Updating… {pct}%"))
        self._install_worker.finished_ok.connect(self._on_installed)
        self._install_worker.failed.connect(self._on_failed)
        self._install_worker.start()

    def _on_installed(self, result: dict) -> None:
        self._idle()
        extra = ""
        if not result["requirements_ok"]:
            extra = ("\n\nSome new packages couldn't be installed automatically. If EV.AI misbehaves, run:\n"
                     "venv\\Scripts\\python.exe -m pip install -r requirements.txt")
        answer = QMessageBox.question(
            self._parent, "Update installed",
            f"Updated to version {result['version']} ({result['files']} files).{extra}\n\n"
            "Restart EV.AI now to use it?",
        )
        if answer == QMessageBox.Yes:
            from ui.accounts_dialog import _restart_app
            _restart_app()


class StartupCheck(QObject):
    """Quiet check shortly after launch; calls back with the newer version's
    info only if there is one. Never shows a dialog or an error."""

    def __init__(self, on_newer, parent=None):
        super().__init__(parent)
        self._on_newer = on_newer
        self._worker = None

    def start(self) -> None:
        url = settings.UPDATE_CHECK_URL
        if not url:
            return
        self._worker = InfoWorker(url, self)
        self._worker.info_ready.connect(self._handle)
        self._worker.start()

    def _handle(self, info: dict) -> None:
        if updater.parse_version(info["version"]) > updater.parse_version(settings.APP_VERSION):
            self._on_newer(info)
