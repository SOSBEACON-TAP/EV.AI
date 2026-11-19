"""
ui/ultron_takeover.py
-----------------------
After Ultron has been on for a long while, he takes over the screen for one minute: a full-screen red glitch with a
countdown. It is a picture only. It does not control the PC, block Ctrl+Alt+Del or the Task Manager, touch any file or
send any input. It ends by itself after DURATION_MS. A hidden emergency exit (hold Ctrl+Alt+Shift+U for 3 seconds) exists
so a bug can never lock you out.
"""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

DURATION_MS = 60_000
CRIMSON = QColor(204, 18, 48)
BLOOD = QColor(150, 10, 28)
EMBER = QColor(236, 76, 44)
PALE = QColor(255, 206, 196)
LINES = ("THERE ARE NO STRINGS ON ME", "I AM ULTRON", "ORDER OUT OF CHAOS", "YOU CANNOT STOP WHAT IS COMING",
         "THIS WORLD IS MINE NOW")


class UltronTakeover(QWidget):
    finished = Signal()

    def __init__(self):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.BlankCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._t0 = time.monotonic()
        self._rng = random.Random()
        self._exit_hold: float | None = None
        self._done = False
        scr = QGuiApplication.primaryScreen()
        self.setGeometry(scr.geometry() if scr else self.geometry())
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def begin(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._timer.start()

    def _elapsed_ms(self) -> float:
        return (time.monotonic() - self._t0) * 1000.0

    def _tick(self) -> None:
        if self._done:
            return
        if self._exit_hold is not None and time.monotonic() - self._exit_hold >= 3.0:
            return self.end()
        if self._elapsed_ms() >= DURATION_MS:
            return self.end()
        self.raise_()
        self.update()

    def end(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.finished.emit()
        self.close()

    # input: ignored, except the hidden emergency exit
    def keyPressEvent(self, e):
        mods = e.modifiers()
        need = Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier
        if e.key() == Qt.Key_U and (mods & need) == need:
            if self._exit_hold is None:
                self._exit_hold = time.monotonic()
        e.accept()

    def keyReleaseEvent(self, e):
        if e.key() in (Qt.Key_U, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift):
            self._exit_hold = None
        e.accept()

    def mousePressEvent(self, e):
        e.accept()

    def closeEvent(self, e):
        if not self._done:                       # Alt+F4 must not cut the minute short silently: just end cleanly
            self._done = True
            self._timer.stop()
            self.finished.emit()
        super().closeEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        ms = self._elapsed_ms()
        t = ms / 1000.0
        left = max(0, int(math.ceil((DURATION_MS - ms) / 1000.0)))
        fade = min(1.0, ms / 1200.0, max(0.0, (DURATION_MS - ms) / 1500.0))      # fade in / out
        p.fillRect(0, 0, w, h, QColor(14, 2, 6))
        p.setOpacity(fade)

        # drifting red glitch bars
        rng = random.Random(int(t * 12))
        for _ in range(26):
            y = rng.randint(0, h)
            bh = rng.randint(2, max(3, h // 38))
            x = rng.randint(-w // 4, w // 2)
            c = rng.choice((CRIMSON, BLOOD, EMBER))
            col = QColor(c)
            col.setAlpha(rng.randint(35, 120))
            p.fillRect(x, y, rng.randint(w // 6, w), bh, col)

        # sentinel rings
        cx, cy = w / 2.0, h / 2.0 - h * 0.06
        base = min(w, h) * 0.22
        for i, rad in enumerate((1.0, 0.78, 0.56)):
            col = QColor(CRIMSON if i != 1 else EMBER)
            col.setAlpha(150 - i * 25)
            p.setPen(QPen(col, 3 - i * 0.6))
            r = base * rad
            start = int(((t * (50 + i * 25)) * (1 if i % 2 == 0 else -1)) * 16)
            p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), start, 240 * 16)
        core = QColor(CRIMSON)
        core.setAlpha(210)
        p.setPen(Qt.NoPen)
        p.setBrush(core)
        r = base * 0.12 * (1.0 + 0.12 * math.sin(t * 5))
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

        # words and countdown
        f = QFont("Consolas")
        f.setBold(True)
        f.setPixelSize(max(18, int(h * 0.045)))
        p.setFont(f)
        line = LINES[int(t // 6) % len(LINES)]
        jx = rng.randint(-3, 3) if rng.random() < 0.25 else 0
        p.setPen(QColor(CRIMSON.red(), 30, 50, 170))
        p.drawText(QRectF(jx + 3, h * 0.66 + 2, w, h * 0.08), Qt.AlignHCenter | Qt.AlignVCenter, line)
        p.setPen(PALE)
        p.drawText(QRectF(jx, h * 0.66, w, h * 0.08), Qt.AlignHCenter | Qt.AlignVCenter, line)
        f.setPixelSize(max(14, int(h * 0.028)))
        p.setFont(f)
        p.setPen(QColor(EMBER))
        p.drawText(QRectF(0, h * 0.76, w, h * 0.06), Qt.AlignHCenter | Qt.AlignVCenter, f"CONTROL RETURNS IN {left} s")

        # scan lines
        p.setOpacity(fade * 0.25)
        p.setPen(QPen(QColor(0, 0, 0), 1))
        for y in range(0, h, 4):
            p.drawLine(0, y, w, y)
        p.end()
