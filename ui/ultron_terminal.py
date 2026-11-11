"""ULTRON TERMLINK: a green phosphor terminal window.
Left column: the code (or command) you type or paste, with hex line addresses.
Right column: what Ultron does with it: an explanation of the code, or the output of a command."""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QTextCursor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget)

GREEN = "#3DFF7A"
DIM = "#1F9A47"
BG = "#020E06"
_QSS = f"""
QDialog {{ background: {BG}; }}
QLabel {{ color: {GREEN}; font-family: Consolas, 'Courier New', monospace; font-size: 13px; }}
QLabel#Dim {{ color: {DIM}; font-size: 11px; }}
QLabel#ColTitle {{ color: {GREEN}; font-size: 13px; letter-spacing: 2px; border-bottom: 1px solid {DIM}; padding-bottom: 3px; }}
QPlainTextEdit, QTextEdit {{ background: #03160A; color: {GREEN}; border: 1px solid {DIM};
    font-family: Consolas, 'Courier New', monospace; font-size: 13px; selection-background-color: {GREEN}; selection-color: #021006; }}
QPushButton {{ background: transparent; color: {GREEN}; border: 1px solid {DIM}; padding: 6px 14px;
    font-family: Consolas, 'Courier New', monospace; font-size: 12px; letter-spacing: 1px; }}
QPushButton:hover {{ background: {GREEN}; color: #021006; }}
QPushButton:disabled {{ color: #145c2c; border-color: #0d3a1c; }}
"""


class _Gutter(QWidget):
    def __init__(self, editor: "CodeEdit"):
        super().__init__(editor)
        self._ed = editor

    def sizeHint(self) -> QSize:
        return QSize(self._ed.gutter_width(), 0)

    def paintEvent(self, e) -> None:
        self._ed.paint_gutter(e)


class CodeEdit(QPlainTextEdit):
    """A code box whose line numbers are hex addresses (0x5000, 0x5010, ...), like the terminal in the picture."""

    def __init__(self):
        super().__init__()
        self._gutter = _Gutter(self)
        self.blockCountChanged.connect(self._update_width)
        self.updateRequest.connect(self._scroll_gutter)
        self._update_width()
        f = QFont("Consolas", 11)
        f.setStyleHint(QFont.Monospace)
        self.setFont(f)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def gutter_width(self) -> int:
        return 12 + self.fontMetrics().horizontalAdvance("0x0000")

    def _update_width(self) -> None:
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _scroll_gutter(self, rect, dy) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_width()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, e) -> None:
        p = QPainter(self._gutter)
        p.fillRect(e.rect(), QColor("#021208"))
        p.setPen(QColor(DIM))
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top():
                p.drawText(0, top, self._gutter.width() - 6, self.fontMetrics().height(), Qt.AlignRight, f"0x{0x5000 + n * 0x10:04X}")
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            n += 1


class _Scanlines(QWidget):
    """Faint horizontal lines over everything, like an old monitor. Lets clicks through."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setPen(QColor(0, 0, 0, 55))
        for y in range(0, self.height(), 3):
            p.drawLine(0, y, self.width(), y)


class UltronTerminal(QDialog):
    def __init__(self, core, parent=None):
        super().__init__(parent)
        self._core = core
        self.setWindowTitle("ULTRON TERMLINK")
        self.resize(1040, 640)
        self.setStyleSheet(_QSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(8)

        root.addWidget(QLabel("Welcome to ULTRON Industries (TM) Termlink"))
        root.addWidget(QLabel("Terminal ready. Attempts remaining: ■ ■ ■"))
        hint = QLabel("Left: paste code to EXPLAIN it, or say or type what you want and press WRITE CODE FOR ME. "
                      "A line starting with > runs as a Windows command.")
        hint.setObjectName("Dim")
        root.addWidget(hint)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        left, right = QVBoxLayout(), QVBoxLayout()
        lt = QLabel("1.  EXPLAIN CODE   (your input)")
        lt.setObjectName("ColTitle")
        rt = QLabel("2.  OUTPUT   (what Ultron does)")
        rt.setObjectName("ColTitle")
        self.code = CodeEdit()
        self.code.setPlaceholderText("Paste code to explain...\nor say: write a python program that ...\nor run: > ipconfig")
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        left.addWidget(lt)
        left.addWidget(self.code, 1)
        right.addWidget(rt)
        right.addWidget(self.out, 1)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        root.addLayout(cols, 1)

        row = QHBoxLayout()
        self.explain_btn = QPushButton("EXPLAIN CODE   (Ctrl+Enter)")
        self.explain_btn.clicked.connect(self.explain)
        self.write_btn = QPushButton("WRITE CODE FOR ME")
        self.write_btn.clicked.connect(self.write)
        self.run_code_btn = QPushButton("RUN CODE")
        self.run_code_btn.setToolTip("Runs the code Ultron just wrote (or the code in the left box) and shows what it prints")
        self.run_code_btn.clicked.connect(self.run_code)
        self.run_btn = QPushButton("RUN LINE AS COMMAND")
        self.run_btn.clicked.connect(self.run_line)
        copy_btn = QPushButton("COPY OUTPUT")
        copy_btn.clicked.connect(self._copy)
        save_btn = QPushButton("SAVE CODE")
        save_btn.clicked.connect(self._save)
        clear_btn = QPushButton("CLEAR")
        clear_btn.clicked.connect(self._clear)
        exit_btn = QPushButton("[Esc] EXIT")
        exit_btn.clicked.connect(self.close)
        for b in (self.explain_btn, self.write_btn, self.run_code_btn, self.run_btn, copy_btn, save_btn, clear_btn):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(exit_btn)
        root.addLayout(row)

        self._scan = _Scanlines(self)
        self._scan.raise_()
        self._say("ULTRON", "Give me code and I will tell you what it does, and what is wrong with it.")

    # -- helpers ------------------------------------------------------------------------------
    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._scan.setGeometry(self.rect())
        self._scan.raise_()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.close()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self.explain()
        else:
            super().keyPressEvent(e)

    def _say(self, who: str, text: str, color: str = GREEN) -> None:
        import html
        for ln in str(text).splitlines() or [""]:
            safe = html.escape(ln).replace("  ", "&nbsp;&nbsp;")
            self.out.append(f'<span style="color:{color}">&gt;{safe}</span>' if ln.strip() else "")
        self.out.moveCursor(QTextCursor.End)

    def _clear(self) -> None:
        self.code.clear()
        self.out.clear()
        self._last_code = self._last_output = self._last_request = ""

    def _busy(self, on: bool) -> None:
        self.explain_btn.setDisabled(on)
        self.write_btn.setDisabled(on)
        self.run_code_btn.setDisabled(on)
        self.run_btn.setDisabled(on)

    def _current_line(self) -> str:
        sel = self.code.textCursor().selectedText().replace(" ", "\n").strip()
        return sel or self.code.textCursor().block().text().strip()

    # -- code writing ---------------------------------------------------------------------------
    def wants(self, text: str) -> bool:
        """While this window is open, whatever you type or say in the main box is a coding request (unless it is a > command)."""
        return self.isVisible() and not text.strip().startswith(">")

    def request_code(self, text: str) -> None:
        self.code.setPlainText(text.strip())
        self.write()

    def write(self) -> None:
        text = self.code.toPlainText().strip()
        if not text or text.startswith(">"):
            self._say("ULTRON", "Tell me what to write. For example: a python program that renames all files in a folder.", "#FFB020")
            return
        self._last_request = text
        self._say("ULTRON", "Writing...", DIM)
        self._busy(True)
        self._core.write_code(text, self._show_code, lambda e: (self._busy(False), self._say("ULTRON", e, "#FF5050")))

    def _show_code(self, code: str) -> None:
        import html
        self._busy(False)
        self._last_output = code
        self._last_code = code
        self.out.append('<pre style="color:%s; margin:0">%s</pre>' % (GREEN, html.escape(code)))
        self.out.moveCursor(QTextCursor.End)

    _last_output = ""
    _last_code = ""
    _last_request = ""

    def run_code(self) -> None:
        """Runs the code Ultron just wrote; if there is none, the code in the left box."""
        left = self.code.toPlainText().strip()
        edited = bool(left) and left != self._last_request and not left.startswith(">")
        code = left if edited or not self._last_code else self._last_code
        if not code.strip():
            self._say("ULTRON", "There is nothing to run yet. Ask me to write something, or paste code on the left.", "#FFB020")
            return
        self._say("ULTRON", "Running...", DIM)
        self._busy(True)
        started = self._core.run_code(
            code,
            lambda r: (self._busy(False), self._say("ULTRON", "OUTPUT:\n" + r)),
            lambda e: (self._busy(False), self._say("ULTRON", e, "#FF5050")))
        if not started:
            self._busy(False)
            self._say("ULTRON", "Not run.", "#FFB020")

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._last_output or self.out.toPlainText())

    def _save(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        text = self._last_output or self.out.toPlainText()
        if not text.strip():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save the code", "ultron_code.py", "All files (*)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                self._say("ULTRON", f"Saved: {path}")
            except OSError as e:
                self._say("ULTRON", f"Couldn't save: {e}", "#FF5050")

    # -- actions --------------------------------------------------------------------------------
    def explain(self) -> None:
        text = self.code.toPlainText().strip()
        if not text:
            self._say("ULTRON", "There is nothing to explain. Paste some code on the left.", "#FFB020")
            return
        first = text.splitlines()[0].strip()
        if first.startswith(">") and len(text.splitlines()) == 1:     # a single ">" line is a command, not code
            self.run_line()
            return
        self._say("ULTRON", "Reading your code...", DIM)
        self._busy(True)
        self._core.explain_code(
            text,
            lambda r: (self._busy(False), self._say("ULTRON", r)),
            lambda e: (self._busy(False), self._say("ULTRON", e, "#FF5050")))

    def run_line(self) -> None:
        line = self._current_line()
        cmd = line[1:].strip() if line.startswith(">") else line
        if not cmd:
            self._say("ULTRON", "Put a command on a line, for example: > ipconfig", "#FFB020")
            return
        self._say("ULTRON", f"{self._core.shell.cwd}> {cmd}", DIM)
        self._busy(True)
        started = self._core.run_command(
            cmd,
            lambda r: (self._busy(False), self._say("ULTRON", r or "(no output)")),
            lambda e: (self._busy(False), self._say("ULTRON", e, "#FF5050")))
        if not started:
            self._busy(False)
            self._say("ULTRON", "Cancelled.", "#FFB020")
