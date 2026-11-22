"""
ui/spaces_dialog.py
---------------------
Mission Spaces: start a space with one click, and EDIT what each one opens (apps, websites, folders), add a new one, or
delete one. Nothing here closes anything on the computer.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from core import spaces, user_prefs
from ui.theme import dialog_stylesheet


class _ItemList(QWidget):
    """A list of things (apps / websites / folders) with Add and Remove."""

    def __init__(self, hint: str, add_text: str, browse: bool = False, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(hint))
        self.list = QListWidget()
        lay.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton(add_text)
        add.clicked.connect(self._add)
        rem = QPushButton("Remove selected")
        rem.clicked.connect(lambda: [self.list.takeItem(self.list.row(i)) for i in self.list.selectedItems()])
        row.addWidget(add)
        if browse:
            b = QPushButton("Browse…")
            b.clicked.connect(self._browse)
            row.addWidget(b)
        row.addWidget(rem)
        lay.addLayout(row)
        self._prompt = add_text

    def set_items(self, items) -> None:
        self.list.clear()
        self.list.addItems([str(i) for i in items])

    def items(self) -> list[str]:
        return [self.list.item(i).text().strip() for i in range(self.list.count()) if self.list.item(i).text().strip()]

    def _add(self) -> None:
        text, ok = QInputDialog.getText(self, "Add", self._prompt + ":")
        if ok and text.strip():
            self.list.addItem(text.strip())

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a folder")
        if d:
            self.list.addItem(d)


class SpaceEditor(QDialog):
    def __init__(self, name: str, data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit space: {name}")
        self.setMinimumSize(460, 420)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        self._name = name
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        self.apps = _ItemList("Programs to open (a name like 'code', 'chrome', 'steam', or a full path to an .exe):", "Add a program")
        self.urls = _ItemList("Websites to open:", "Add a website (https://...)")
        self.folders = _ItemList("Folders to open:", "Add a folder path", browse=True)
        for w, t in ((self.apps, "PROGRAMS"), (self.urls, "WEBSITES"), (self.folders, "FOLDERS")):
            tabs.addTab(w, t)
        self.apps.set_items(data.get("apps", []))
        self.urls.set_items(data.get("urls", []))
        self.folders.set_items(data.get("folders", []))
        lay.addWidget(tabs)
        self.focus = QCheckBox("Suggest Focus mode when this space starts")
        self.focus.setChecked(bool(data.get("focus")))
        lay.addWidget(self.focus)
        row = QHBoxLayout()
        ok = QPushButton("SAVE")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def values(self) -> dict:
        return {"apps": self.apps.items(), "urls": self.urls.items(), "folders": self.folders.items(), "focus": self.focus.isChecked()}


class SpacesDialog(QDialog):
    started = Signal(str)             # a space name to start
    message = Signal(str)             # something to say in the conversation

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mission Spaces")
        self.setMinimumSize(380, 300)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        self._lay = QVBoxLayout(self)
        self._rebuild()

    def _rebuild(self) -> None:
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                while it.layout().count():
                    w = it.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
        self._lay.addWidget(QLabel("Start a space to open its programs, websites and folders. Nothing is closed.\n"
                                   "Use Edit to change what a space opens."))
        for sp in spaces.list_spaces()["spaces"]:
            row = QHBoxLayout()
            b = QPushButton(sp["name"].upper())
            b.setMinimumHeight(34)
            b.setToolTip("Opens: " + (", ".join(sp["apps"] + sp["urls"] + sp["folders"]) or "nothing yet. Press Edit to add things."))
            b.clicked.connect(lambda _=False, n=sp["name"]: self._start(n))
            e = QPushButton("Edit")
            e.clicked.connect(lambda _=False, s=sp: self._edit(s))
            d = QPushButton("Delete")
            d.clicked.connect(lambda _=False, n=sp["name"]: (spaces.delete_space(n), self._rebuild()))
            row.addWidget(b, 1)
            row.addWidget(e)
            row.addWidget(d)
            self._lay.addLayout(row)
        new = QPushButton("＋ New space…")
        new.clicked.connect(self._new)
        snap = QPushButton("Save what is open now as a new space…")
        snap.clicked.connect(self._snap)
        self._lay.addWidget(new)
        self._lay.addWidget(snap)

    def _start(self, name: str) -> None:
        self.accept()
        self.started.emit(name)

    def _edit(self, sp: dict) -> None:
        dlg = SpaceEditor(sp["name"], sp, self)
        if dlg.exec() == QDialog.Accepted:
            v = dlg.values()
            r = spaces.save_space(sp["name"], v["apps"], v["urls"], v["folders"], v["focus"])
            if "error" in r:
                self.message.emit(r["error"])
        self._rebuild()

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, "New space", "Name for the space (for example 'Project X'):")
        if not ok or not name.strip():
            return
        dlg = SpaceEditor(name.strip(), {}, self)
        if dlg.exec() == QDialog.Accepted:
            v = dlg.values()
            r = spaces.save_space(name.strip(), v["apps"], v["urls"], v["folders"], v["focus"])
            if "error" in r:
                self.message.emit(r["error"])
        self._rebuild()

    def _snap(self) -> None:
        name, ok = QInputDialog.getText(self, "New space", "Name for this space (for example 'Project X'):")
        if ok and name.strip():
            r = spaces.snapshot_space(name.strip())
            self.message.emit(f"Saved space '{name.strip()}' with: " + ", ".join(r["apps"]) if "apps" in r else r.get("error", "Could not save."))
            self._rebuild()
