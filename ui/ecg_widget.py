"""
ui/ecg_widget.py
------------------
A glowing red heartbeat line on black, scrolling to the left like a hospital monitor (Baymax's left side).
It is an illustration: it is NOT measuring anything about you.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


def _beat(x: float) -> float:
    """One heartbeat, x in 0..1 -> height -1..1 (flat, small bump, sharp spike, dip, rounded bump, flat)."""
    def bump(c, w, a):
        return a * math.exp(-((x - c) / w) ** 2)
    return (bump(0.16, 0.035, 0.18) + bump(0.30, 0.012, -0.20) + bump(0.335, 0.014, 1.0)
            + bump(0.37, 0.014, -0.42) + bump(0.58, 0.05, 0.30))


class EcgMonitor(QWidget):
    BEAT_SECONDS = 1.1          # one beat takes this long to scroll past
    SHOWN_BEATS = 2.6           # how many beats fit across the screen

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, e) -> None:  # noqa: N802
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    def _tick(self) -> None:
        self._t += 0.033
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(4, 2, 4))
        p.setPen(QPen(QColor(255, 60, 60, 22), 1))                       # faint grid
        for x in range(0, w, 20):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 20):
            p.drawLine(0, y, w, y)
        mid, amp = h * 0.58, h * 0.36
        path = QPainterPath()
        steps = max(60, w // 2)
        for i in range(steps + 1):
            fx = i / steps                                              # 0 (left, old) .. 1 (right, newest)
            beats = fx * self.SHOWN_BEATS + self._t / self.BEAT_SECONDS
            y = mid - _beat(beats % 1.0) * amp
            pt = QPointF(fx * w, y)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        for width, alpha in ((9, 28), (5, 60), (2.4, 255)):              # glow, then the bright line
            col = QColor(255, 40, 50, alpha) if width > 3 else QColor(255, 120, 120, alpha)
            p.setPen(QPen(col, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)
        f = QFont()
        f.setPointSize(7)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 120, 120, 170))
        p.drawText(QRectF(8, 4, w - 16, 14), Qt.AlignLeft | Qt.AlignVCenter, "HEARTBEAT  (illustration, not a measurement)")
        p.end()
