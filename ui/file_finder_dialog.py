"""AI File Finder window: type what you're looking for in plain words, get ranked
matches with their folder, date and size, then Open the file or its folder.
Searches file NAMES from a local index (core/file_finder.py); contents are never read."""

from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from core import file_finder, user_prefs
from ui.theme import dialog_stylesheet


class _IndexWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(file_finder.build_index(90.0))
        except Exception as e:  # noqa: BLE001
            self.done.emit({"error": str(e)})


class _SearchWorker(QThread):
    done = Signal(object)

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self._query = query

    def run(self) -> None:
        try:
            self.done.emit(file_finder.search(self._query, limit=40))
        except Exception as e:  # noqa: BLE001
            self.done.emit({"error": str(e)})


class FileFinderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI File Finder")
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        self.resize(640, 520)
        self._worker = None
        self._index_worker = None
        self._results = []
        root = QVBoxLayout(self)

        row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("e.g. find my EV AI python file · images in Downloads · Arduino projects")
        self._query.returnPressed.connect(self._search)
        row.addWidget(self._query, 1)
        go = QPushButton("Search")
        go.clicked.connect(self._search)
        row.addWidget(go)
        root.addLayout(row)

        self._status = QLabel("")
        self._status.setProperty("role", "sub")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _i: self._open(False))
        root.addWidget(self._list, 1)

        btns = QHBoxLayout()
        self._open_btn = QPushButton("Open")
        self._open_btn.clicked.connect(lambda: self._open(False))
        self._folder_btn = QPushButton("Show in folder")
        self._folder_btn.clicked.connect(lambda: self._open(True))
        self._refresh_btn = QPushButton("Refresh index")
        self._refresh_btn.clicked.connect(self._refresh_index)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        for b in (self._open_btn, self._folder_btn, self._refresh_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(close)
        root.addLayout(btns)
        self._show_index_status()
        self._query.setFocus()

    # -- index ------------------------------------------------------------------
    def _show_index_status(self) -> None:
        count, when = file_finder.index_info()
        if count == 0:
            self._status.setText("No index yet — it will be built the first time you search (a few seconds).")
        else:
            stamp = datetime.fromtimestamp(when).strftime("%Y-%m-%d %H:%M") if when else "?"
            self._status.setText(f"{count:,} files indexed (updated {stamp}). Only names and folders are stored.")

    def _refresh_index(self) -> None:
        self._refresh_btn.setEnabled(False)
        self._status.setText("Indexing your folders…")
        self._index_worker = _IndexWorker(self)
        self._index_worker.done.connect(self._index_done)
        self._index_worker.start()

    def _index_done(self, info) -> None:
        self._refresh_btn.setEnabled(True)
        if "error" in info:
            self._status.setText(f"Indexing failed: {info['error']}")
        else:
            self._status.setText(f"Indexed {info['files']:,} files in {info['seconds']}s"
                                 + (" (stopped early at the time limit)" if info["partial"] else "") + ".")

    # -- search -------------------------------------------------------------------
    def _search(self) -> None:
        text = self._query.text().strip()
        if not text:
            return
        self._status.setText("Searching…")
        self._list.clear()
        self._worker = _SearchWorker(text, self)
        self._worker.done.connect(self._show_results)
        self._worker.start()

    def _show_results(self, result) -> None:
        if "error" in result:
            self._status.setText(f"Search failed: {result['error']}")
            return
        self._list.clear()
        self._results = list(result["results"])
        for r in result["results"]:
            kind = "📁" if r["is_dir"] else "📄"
            size = "" if r["is_dir"] else f" · {file_finder.human_size(r['size'])}"
            item = QListWidgetItem(f"{kind} {r['name']}\n     {r['path'] if r['is_dir'] else r['folder']}\n"
                                   f"     modified {r['modified']}{size}")
            item.setData(Qt.UserRole, r["n"] - 1)
            self._list.addItem(item)
        n = result["count"]
        self._status.setText(f"{n} result{'s' if n != 1 else ''}." if n else
                             "Nothing matched. Try other words, or press Refresh index.")
        if n:
            self._list.setCurrentRow(0)

    def _open(self, reveal: bool) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        found = self._results[item.data(Qt.UserRole)]
        out = file_finder.open_path(found["path"], reveal=reveal and not found["is_dir"])
        if "error" in out:
            self._status.setText(out["error"])
        elif out.get("note"):
            self._status.setText(out["note"])

    def closeEvent(self, event) -> None:
        for w in (self._worker, self._index_worker):
            if w is not None and w.isRunning():
                w.wait(5000)
        super().closeEvent(event)
