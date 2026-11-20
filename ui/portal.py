"""
ui/portal.py
--------------
AI Portal: a small floating bar that opens anywhere with Ctrl+Alt+Space. If you had text selected in another app,
Command Anywhere offers to explain, rewrite, translate or summarize it. The answer shows here and can be copied.
The selected text is only read when you press the hotkey, and your clipboard is put back afterwards.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

VERBS = (("Explain", "Explain this in simple words"), ("Rewrite", "Rewrite this to be clearer and better written"),
         ("Translate", "Translate this into English (or into Hindi if it is already English)"),
         ("Summarize", "Summarize this in a few short bullet points"))


def grab_selection(callback) -> None:
    """Copy the selected text of the program in front, call callback(text), and restore the clipboard.
    Runs on timers so the interface never blocks. Windows only; gives "" when nothing was selected."""
    cb = QGuiApplication.clipboard()
    saved = cb.text()
    marker = f"__ev_portal_{id(callback)}__"
    cb.setText(marker)

    def press():
        try:
            import pyautogui
            for k in ("alt", "ctrl", "shift"):          # the hotkey keys may still be held down
                pyautogui.keyUp(k)
            pyautogui.hotkey("ctrl", "c")
        except Exception:
            pass

    def read():
        text = cb.text()
        cb.setText(saved)
        callback("" if text == marker else text)

    QTimer.singleShot(350, press)
    QTimer.singleShot(750, read)


class AIPortal(QWidget):
    def __init__(self, ask):
        """ask(prompt: str) sends the prompt to EV; the answer is given back with show_reply()."""
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._ask = ask
        self._selected = ""
        self.setObjectName("AIPortal")
        self.setFixedWidth(520)
        self.setStyleSheet(
            "#AIPortal { background: #0B1220; border: 1px solid #5AA0E6; border-radius: 14px; }"
            "QLabel { color: #D6ECFA; font-size: 12px; } QLabel#hint { color: #7FA0C0; font-size: 10px; }"
            "QLineEdit { background: #0F1A2E; color: #EAF6FF; border: 1px solid #2F5C99; border-radius: 8px; padding: 7px; font-size: 13px; }"
            "QPushButton { background: #11305C; color: #D6ECFA; border: 1px solid #3D7BC8; border-radius: 8px; padding: 5px 10px; }"
            "QPushButton:hover { background: #1A4A8A; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        self._title = QLabel("EV PORTAL")
        self._title.setObjectName("hint")
        lay.addWidget(self._title)
        self._sel = QLabel("")
        self._sel.setWordWrap(True)
        self._sel.setVisible(False)
        lay.addWidget(self._sel)
        self._verbs = QWidget()
        vl = QHBoxLayout(self._verbs)
        vl.setContentsMargins(0, 0, 0, 0)
        for label, prompt in VERBS:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, p=prompt: self._run(p))
            vl.addWidget(b)
        self._verbs.setVisible(False)
        lay.addWidget(self._verbs)
        self._line = QLineEdit()
        self._line.setPlaceholderText("Ask EV anything…  (Esc closes)")
        self._line.returnPressed.connect(self._submit)
        lay.addWidget(self._line)
        self._reply = QLabel("")
        self._reply.setWordWrap(True)
        self._reply.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._reply.setVisible(False)
        lay.addWidget(self._reply)
        self._copy = QPushButton("Copy answer")
        self._copy.setVisible(False)
        self._copy.clicked.connect(lambda: QApplication.clipboard().setText(self._reply.text()))
        lay.addWidget(self._copy)

    def open_with(self, selected: str) -> None:
        self._selected = (selected or "").strip()[:6000]
        has = bool(self._selected)
        self._sel.setVisible(has)
        self._verbs.setVisible(has)
        self._sel.setText("Selected: " + (self._selected[:140] + ("…" if len(self._selected) > 140 else "")) if has else "")
        self._reply.setVisible(False)
        self._copy.setVisible(False)
        self._line.clear()
        scr = QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(scr.center().x() - self.width() // 2, scr.top() + int(scr.height() * 0.22))
        self.show()
        self.raise_()
        self.activateWindow()
        self._line.setFocus()

    def _run(self, instruction: str) -> None:
        self._reply.setText("Thinking…")
        self._reply.setVisible(True)
        self.adjustSize()
        self._ask(f"{instruction}. Reply with only the result, no preamble.\n\n{self._selected}")

    def _submit(self) -> None:
        q = self._line.text().strip()
        if not q:
            return
        self._line.clear()
        self._reply.setText("Thinking…")
        self._reply.setVisible(True)
        self.adjustSize()
        self._ask(f"{q}\n\n{self._selected}" if self._selected else q)

    def show_reply(self, text: str) -> None:
        if not self.isVisible():
            return
        self._reply.setText(text)
        self._reply.setVisible(True)
        self._copy.setVisible(True)
        self.adjustSize()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)
