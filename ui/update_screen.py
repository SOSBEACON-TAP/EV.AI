"""
ui/update_screen.py
--------------------
Full-screen "UPDATING..." screen shown while a new version downloads: black
background, turning cyan gears and a segmented progress bar with the real
download percentage.
"""

import math

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.startup_screen import _SegBar

_CYAN = QColor("#35e5e5")
_BG = QColor(0, 0, 0)


def _gear_path(cx: float, cy: float, r: float, teeth: int, angle: float) -> QPainterPath:
    outer, inner = r, r * 0.8
    path = QPainterPath()
    steps = teeth * 4
    for i in range(steps):
        a = math.radians(angle) + i * 2 * math.pi / steps
        rad = outer if (i % 4) in (0, 1) else inner
        pt = QPointF(cx + rad * math.cos(a), cy + rad * math.sin(a))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path


class _Gears(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(360, 250)
        self._angle = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(30)

    def _tick(self) -> None:
        self._angle = (self._angle + 1.6) % 360
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            # (centre x, centre y, radius, teeth, direction, start offset)
            gears = [(140, 150, 62, 10, 1, 0), (80, 80, 48, 9, -1, 10), (60, 190, 33, 8, -1, 5),
                     (235, 70, 28, 8, 1, 12), (270, 110, 20, 7, -1, 3)]
            for cx, cy, r, teeth, d, off in gears:
                p.setPen(Qt.NoPen)
                p.setBrush(_CYAN)
                p.drawPath(_gear_path(cx, cy, r, teeth, d * self._angle * (10 / teeth) * 0.6 + off))
                p.setBrush(_BG)
                p.drawEllipse(QPointF(cx, cy), r * 0.42, r * 0.42)
        finally:
            p.end()


class UpdateScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet("background: #000000;")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(26)
        layout.addWidget(_Gears(), alignment=Qt.AlignCenter)
        self._bar = _SegBar()
        self._bar.setFixedWidth(460)
        self._bar.set_color("#35e5e5")
        layout.addWidget(self._bar, alignment=Qt.AlignCenter)
        self._label = QLabel("UPDATING...")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("color: #35e5e5; font-size: 20px; letter-spacing: 4px; background: transparent;")
        layout.addWidget(self._label)

    def show_full(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())
        self.show()
        self.raise_()

    def set_progress(self, percent: int) -> None:
        self._bar.setValue(percent)
        self._label.setText(f"UPDATING... {percent}%")
