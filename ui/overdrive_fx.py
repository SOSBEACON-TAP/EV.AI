"""Overdrive's look, like a tungsten bulb driven too hard: while it runs the screen glows brighter and EV works
faster; in the last seconds the light flickers; then the filament burns out - one white flash, a fading orange glow,
and a dark, cooling-down screen for a few seconds before everything comes back."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

FLICKER_FROM_S = 10        # seconds left when the light starts to flicker
BURN_MS = 900              # the flash and fading glow
DARK_MS = 3200             # how long the screen stays dark and cooling


class OverdriveFX(QWidget):
    """A see-through layer over the window. Never takes the mouse; removes itself when finished."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(window.rect())
        self._window = window
        self._left = 90
        self._phase = "run"                  # run -> burn -> dark -> done
        self._t0 = time.monotonic()
        self._burn_t0 = 0.0
        self._on_done = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(33)
        window.installEventFilter(self)
        self.show()
        self.raise_()

    def eventFilter(self, obj, event):       # keep covering the window when it is resized
        if obj is self._window and event.type().name == "Resize":
            self.setGeometry(self._window.rect())
        return False

    def set_left(self, seconds: int) -> None:
        self._left = seconds

    def burn_out(self, on_done=None) -> None:
        self._phase = "burn"
        self._burn_t0 = time.monotonic()
        self._on_done = on_done

    def stop(self) -> None:
        self._timer.stop()
        try:
            self._window.removeEventFilter(self)
        except Exception:
            pass
        self.hide()
        self.deleteLater()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        now = time.monotonic()
        if self._phase == "run":
            glow = 0.5 + 0.5 * math.sin(now * 3.0)
            # brighter: a warm light bloom over everything (kept gentle so it does not burn your eyes)
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            p.fillRect(0, 0, w, h, QColor(255, 150, 40, int(14 + 10 * glow)))
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            if self._left <= FLICKER_FROM_S:     # a failing bulb: the light stutters, more and more as time runs out
                urgency = 1.0 - self._left / FLICKER_FROM_S
                rnd = random.Random(int(now * 14))
                if rnd.random() < 0.15 + 0.5 * urgency:
                    p.fillRect(0, 0, w, h, QColor(0, 0, 0, int(60 + 120 * urgency * rnd.random())))
                elif rnd.random() < 0.2 * urgency:
                    p.setCompositionMode(QPainter.CompositionMode_Plus)
                    p.fillRect(0, 0, w, h, QColor(255, 230, 190, int(40 * urgency)))
            p.end()
            return
        if self._phase == "burn":
            k = (now - self._burn_t0) * 1000.0 / BURN_MS
            if k >= 1.0:
                self._phase = "dark"
                self._burn_t0 = now
                if self._on_done:
                    cb, self._on_done = self._on_done, None
                    try:
                        cb()
                    except Exception:
                        pass
                k = 0.0
            else:
                flash = max(0.0, 1.0 - k * 3.0)               # the white pop
                p.fillRect(0, 0, w, h, QColor(255, 244, 225, int(235 * flash)))
                glow = QRadialGradient(w / 2, h / 2, max(w, h) * 0.6)    # the filament glow fading out
                glow.setColorAt(0.0, QColor(255, 140, 30, int(190 * (1 - k))))
                glow.setColorAt(1.0, QColor(0, 0, 0, int(240 * k)))
                p.fillRect(0, 0, w, h, glow)
                p.end()
                return
        # dark: the bulb has gone out; a last orange glow dies in the middle, then the screen clears
        k = (now - self._burn_t0) * 1000.0 / DARK_MS
        if k >= 1.0:
            p.end()
            self.stop()
            return
        dim = 245 if k < 0.6 else int(245 * (1.0 - (k - 0.6) / 0.4))
        p.fillRect(0, 0, w, h, QColor(0, 0, 0, dim))
        ember = max(0.0, 1.0 - k * 2.5)
        if ember > 0:
            g = QRadialGradient(w / 2, h / 2, 90)
            g.setColorAt(0.0, QColor(255, 120, 20, int(160 * ember)))
            g.setColorAt(1.0, QColor(255, 120, 20, 0))
            p.fillRect(0, 0, w, h, g)
        p.end()
