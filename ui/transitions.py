"""Screen transitions when the mode changes: the old look dissolves slowly into the new colours, and switching to
Ultron corrupts the old screen (glitching, tearing, turning red) before it dissolves into Ultron's."""
from __future__ import annotations

import random
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class ModeTransition(QWidget):
    """Lies on top of the window showing a snapshot of the OLD screen (taken before the change) and fades it away,
    so the new look is revealed slowly."""

    def __init__(self, window: QWidget, old: QPixmap, glitch: bool = False, ms: int = 1600):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(window.rect())
        self._old = old
        self._glitch = glitch
        self._ms = ms
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)
        self.show()
        self.raise_()

    def _t(self) -> float:
        return min(1.0, (time.monotonic() - self._t0) * 1000.0 / self._ms)

    def _tick(self) -> None:
        if self._t() >= 1.0:
            self._timer.stop()
            self.hide()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        t = self._t()
        p = QPainter(self)
        w, h = self.width(), self.height()
        dpr = self._old.devicePixelRatio() or 1.0
        if not self._glitch:
            k = 1.0 - t
            p.setOpacity(k * k * (3 - 2 * k))                   # slow, smooth dissolve
            p.drawPixmap(0, 0, self._old)
            p.end()
            return
        # corruption: the first part tears and reddens the old screen, the rest dissolves it into the new one
        ramp = min(1.0, t / 0.55)
        fade = 1.0 if t < 0.55 else max(0.0, 1.0 - (t - 0.55) / 0.45)
        frame = int(time.monotonic() * 18)
        n = 26
        bh = h / n
        p.setOpacity(fade)
        for i in range(n):
            rnd = random.Random(frame * 7919 + i * 131)
            off = 0.0
            if rnd.random() < 0.55 * ramp:
                off = (rnd.random() - 0.5) * 2 * 90 * ramp
            src = QRectF(0, i * bh * dpr, w * dpr, bh * dpr)
            p.drawPixmap(QRectF(off, i * bh, w, bh + 1), self._old, src)
            if rnd.random() < 0.25 * ramp:                      # a ghost of the band, shifted, like a colour split
                p.setOpacity(fade * 0.35)
                p.drawPixmap(QRectF(-off * 0.6, i * bh, w, bh + 1), self._old, src)
                p.setOpacity(fade)
        veil = QColor(255, 24, 30, int(150 * ramp * fade))      # the screen turns red
        p.fillRect(0, 0, w, h, veil)
        rnd = random.Random(frame * 31337)
        for _ in range(int(6 * ramp)):                           # bright red and black tearing bars
            y = rnd.random() * h
            p.fillRect(0, int(y), w, rnd.randint(2, 14), QColor(255, 40, 50, int(150 * fade)) if rnd.random() < 0.6 else QColor(0, 0, 0, int(190 * fade)))
        p.setOpacity(fade * 0.5)
        for y in range(0, h, 3):                                  # scan lines
            p.fillRect(0, y, w, 1, QColor(0, 0, 0, 90))
        p.end()
