"""Error Doctor window: runs core/error_doctor.py's checks in the background
and lists each result with a plain-language fix. 'Copy report' puts the
plain-text version on the clipboard for sharing."""

import html

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout

from core import error_doctor, user_prefs
from core.log_buffer import LOG
from ui.theme import dialog_stylesheet

_COLORS = {error_doctor.OK: "#3ecf8e", error_doctor.WARN: "#f5b942", error_doctor.BAD: "#ff5c5c"}
_TAGS = {error_doctor.OK: "OK", error_doctor.WARN: "CHECK", error_doctor.BAD: "FIX"}


class _CheckWorker(QThread):
    done = Signal(object)

    def __init__(self, video_on: bool, parent=None):
        super().__init__(parent)
        self._video_on = video_on

    def run(self) -> None:
        try:
            results = error_doctor.run_checks(self._video_on, LOG.get_text())
        except Exception as e:  # noqa: BLE001
            results = [(error_doctor.BAD, "Error Doctor itself hit a problem", str(e))]
        self.done.emit(results)


class ErrorDoctorDialog(QDialog):
    def __init__(self, video_mode_on: bool = False, parent=None):
        super().__init__(parent)
        self._video_on = video_mode_on
        self._results: list = []
        self._worker = None
        self.setWindowTitle("Error Doctor")
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        self.resize(560, 460)
        layout = QVBoxLayout(self)
        self._view = QTextEdit()
        self._view.setReadOnly(True)
        layout.addWidget(self._view, 1)
        row = QHBoxLayout()
        self._again = QPushButton("Check again")
        self._again.clicked.connect(self.run_checks)
        copy = QPushButton("Copy report")
        copy.clicked.connect(self._copy)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        for b in (self._again, copy, close):
            row.addWidget(b)
        layout.addLayout(row)
        self.run_checks()

    def run_checks(self) -> None:
        self._again.setEnabled(False)
        self._view.setHtml("<p>Checking your setup…</p>")
        self._worker = _CheckWorker(self._video_on, self)
        self._worker.done.connect(self._show)
        self._worker.start()

    def _show(self, results) -> None:
        self._results = results
        problems = sum(1 for r in results if r[0] != error_doctor.OK)
        head = ("<h3>Everything looks fine.</h3>" if not problems
                else f"<h3>{problems} thing(s) to look at</h3>")
        parts = [head]
        for level, title, advice in sorted(results, key=lambda r: r[0] == error_doctor.OK):
            parts.append(
                f"<p><b style='color:{_COLORS[level]}'>[{_TAGS[level]}]</b> <b>{html.escape(title)}</b>"
                + (f"<br><span style='color:#9db4c8'>{html.escape(advice)}</span>" if advice else "")
                + "</p>")
        self._view.setHtml("".join(parts))
        self._again.setEnabled(True)

    def _copy(self) -> None:
        QApplication.clipboard().setText(error_doctor.format_report(self._results))

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(4000)
        super().closeEvent(event)
