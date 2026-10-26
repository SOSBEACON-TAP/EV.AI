"""Quick Actions: a window to see, create, edit, run and delete your saved
command chains ("Study Mode" -> open Chrome, YouTube, Notepad ...) without
having to ask the AI. The chains are the same ones the AI saves with
"save a task chain", so both ways stay in sync (core/automation.py).

Each step is one line:
    app chrome         open an application
    site youtube       open a website (name, bookmark or address)
    key ctrl+t         press a key or combo
    type hello world   type text into the focused window
"""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

from tools import automation as automation_tools
from ui.theme import dialog_stylesheet
from core import user_prefs

_VERBS = {  # line prefix -> (tool name, argument name)
    "app": ("open_application", "app_name"),
    "site": ("open_website", "target"),
    "key": ("press_key", "key"),
    "type": ("type_text", "text"),
}
_REVERSE = {tool: (verb, arg) for verb, (tool, arg) in _VERBS.items()}

HINT = ("One step per line:\n"
        "app chrome\nsite youtube\nsite github.com\nkey ctrl+t\ntype hello")


def steps_to_text(steps: list) -> str:
    lines = []
    for step in steps:
        tool, args = step.get("tool"), step.get("arguments") or {}
        if tool in _REVERSE:
            verb, arg = _REVERSE[tool]
            lines.append(f"{verb} {args.get(arg, '')}".rstrip())
        else:
            lines.append(f"# {tool} (kept as is)")
    return "\n".join(lines)


def text_to_steps(text: str, original: list | None = None) -> tuple[list, list]:
    """Returns (steps, problems). Lines starting with # that stand for steps the
    editor can't express are restored from `original` so nothing is lost."""
    steps, problems = [], []
    extras = [s for s in (original or []) if s.get("tool") not in _REVERSE]
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if extras:
                steps.append(extras.pop(0))
            continue
        verb, _, rest = line.partition(" ")
        verb, rest = verb.lower(), rest.strip()
        if verb not in _VERBS or not rest:
            problems.append(f"Line {number}: “{line}” — start with app, site, key or type, then a value.")
            continue
        tool, arg = _VERBS[verb]
        steps.append({"tool": tool, "arguments": {arg: rest}})
    return steps, problems


class _RunWorker(QThread):
    finished_with = Signal(str)

    def __init__(self, router, name, parent=None):
        super().__init__(parent)
        self._router, self._name = router, name

    def run(self) -> None:
        try:
            result = self._router.execute("run_task_chain", {"name": self._name})
            errors = [r for r in result.get("results", []) if "error" in r or r.get("skipped")]
            if errors:
                self.finished_with.emit(f"Ran “{self._name}” — {len(errors)} step(s) had a problem.")
            else:
                self.finished_with.emit(f"Ran “{self._name}” ({result.get('steps_run', 0)} steps).")
        except Exception as e:  # noqa: BLE001
            self.finished_with.emit(f"Couldn't run “{self._name}”: {e}")


class QuickActionsDialog(QDialog):
    def __init__(self, router, parent=None):
        super().__init__(parent)
        self._router = router
        self._store = automation_tools.get_store()
        self._worker = None
        self._loaded_steps: list = []
        self.setWindowTitle("Quick Actions")
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        self.resize(640, 420)

        outer = QHBoxLayout(self)
        left = QVBoxLayout()
        title = QLabel("YOUR COMMANDS")
        title.setProperty("role", "section")
        left.addWidget(title)
        self._list = QListWidget()
        self._list.currentTextChanged.connect(self._on_pick)
        left.addWidget(self._list, 1)
        new_btn = QPushButton("+ New command")
        new_btn.clicked.connect(self._new)
        left.addWidget(new_btn)
        outer.addLayout(left, 2)

        right = QVBoxLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("Command name, e.g. study mode")
        right.addWidget(self._name)
        self._steps = QPlainTextEdit()
        self._steps.setPlaceholderText(HINT)
        right.addWidget(self._steps, 1)
        note = QLabel("Say or type the name to run it (for example “run study mode”), or press Run here.")
        note.setWordWrap(True)
        note.setProperty("role", "sub")
        right.addWidget(note)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        right.addWidget(self._status)
        row = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._save)
        self._run_btn = QPushButton("Run")
        self._run_btn.clicked.connect(self._run)
        self._del_btn = QPushButton("Delete")
        self._del_btn.clicked.connect(self._delete)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        for b in (self._save_btn, self._run_btn, self._del_btn, close_btn):
            row.addWidget(b)
        right.addLayout(row)
        outer.addLayout(right, 3)
        self._refresh()

    # -- list ---------------------------------------------------------
    def _refresh(self, select: str = "") -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for chain in self._store.list_chains().get("chains", []):
            self._list.addItem(chain["name"])
        self._list.blockSignals(False)
        if select:
            for i in range(self._list.count()):
                if self._list.item(i).text() == select:
                    self._list.setCurrentRow(i)
                    return
        if self._list.count():
            self._list.setCurrentRow(0)
        else:
            self._new()

    def _on_pick(self, name: str) -> None:
        if not name:
            return
        steps = self._store.get_chain(name) or []
        self._loaded_steps = steps
        self._name.setText(name)
        self._steps.setPlainText(steps_to_text(steps))
        self._status.setText("")

    def _new(self) -> None:
        self._list.clearSelection()
        self._loaded_steps = []
        self._name.clear()
        self._steps.clear()
        self._name.setFocus()

    # -- actions --------------------------------------------------------
    def _save(self) -> bool:
        name = self._name.text().strip()
        steps, problems = text_to_steps(self._steps.toPlainText(), self._loaded_steps)
        if problems:
            QMessageBox.warning(self, "Quick Actions", "\n".join(problems))
            return False
        result = self._store.save_chain(name, steps)
        if "error" in result:
            QMessageBox.warning(self, "Quick Actions", result["error"])
            return False
        self._status.setText(f"Saved “{name.lower()}” ({len(steps)} steps).")
        self._refresh(select=name.strip().lower())
        return True

    def _run(self) -> None:
        if self._router is None:
            self._status.setText("Commands can't run without the AI tools loaded.")
            return
        if not self._save():
            return
        name = self._name.text().strip().lower()
        self._run_btn.setEnabled(False)
        self._status.setText(f"Running “{name}”…")
        self._worker = _RunWorker(self._router, name, self)
        self._worker.finished_with.connect(self._on_done)
        self._worker.start()

    def _on_done(self, text: str) -> None:
        self._status.setText(text)
        self._run_btn.setEnabled(True)

    def _delete(self) -> None:
        name = self._name.text().strip().lower()
        if not name or self._store.get_chain(name) is None:
            return
        if QMessageBox.question(self, "Delete command", f"Delete “{name}”?") != QMessageBox.Yes:
            return
        self._store.delete_chain(name)
        self._status.setText(f"Deleted “{name}”.")
        self._refresh()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        super().closeEvent(event)
