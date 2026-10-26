"""
ui/floating_ring.py
----------------------
A small, frameless, always-on-top widget showing just EV's AI core ring
plus a tiny input box — used by any "corner UI" mode (Study mode,
combined Serious mode, Observation mode) so the full dashboard can get
out of the way while EV stays reachable.

This is an original design (just the existing AICoreWidget ring in a
compact floating window, draggable, with a one-line input underneath) —
not a reproduction of any franchise's HUD/overlay look.

Interaction:
  - Type a question and press Enter -> emits text_submitted(str).
  - Drag anywhere on the widget (except the input box) to reposition it.
  - Double-click the ring, or click the small "⤢" button, to ask the
    main window to come back -> emits restore_requested().
"""

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton

from core.state import AIState
from ui.animations import AICoreWidget


class FloatingRingWidget(QWidget):
    text_submitted = Signal(str)
    restore_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(150, 190)

        self._drag_offset = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.addStretch(1)
        restore_btn = QPushButton("⤢")
        restore_btn.setFixedSize(20, 20)
        restore_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,20); color: white; "
            "border: none; border-radius: 10px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(255,255,255,50); }"
        )
        restore_btn.clicked.connect(self.restore_requested.emit)
        top_row.addWidget(restore_btn)
        layout.addLayout(top_row)

        self.ring = AICoreWidget()
        self.ring.setFixedSize(110, 110)
        layout.addWidget(self.ring, alignment=Qt.AlignCenter)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask EV...")
        self.input_box.setStyleSheet(
            "QLineEdit { background: rgba(10,14,22,180); color: white; "
            "border: 1px solid rgba(255,255,255,40); border-radius: 6px; "
            "padding: 4px 6px; font-size: 11px; }"
        )
        self.input_box.returnPressed.connect(self._on_submit)
        layout.addWidget(self.input_box)

        self._position_in_corner()

    # -- public API -----------------------------------------------------
    def set_state(self, state: AIState) -> None:
        self.ring.set_state(state)

    def show_in_corner(self) -> None:
        self._position_in_corner()
        self.show()
        self.raise_()

    # -- internal ---------------------------------------------------------
    def _position_in_corner(self) -> None:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        margin = 24
        x = geo.right() - self.width() - margin
        y = geo.bottom() - self.height() - margin
        self.move(x, y)

    def _on_submit(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self.text_submitted.emit(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.input_box.geometry().contains(event.pos()):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event):
        self.restore_requested.emit()
