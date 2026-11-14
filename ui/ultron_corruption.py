"""Switching to Ultron: the screen is slowly corrupted by red static - first the wires (the core's rings and beams), then
the controls and tabs, then the rest of the screen. When most of it is red, an eye forms out of the static and watches
you (its iris follows your mouse); then the picture glitches and the real Ultron screen takes over while the static
clears away.

A see-through window of its own lies over the app (so a picture of the app can be taken underneath it). It is only
cosmetic: any error removes it and the switch still happens."""
from __future__ import annotations

import os
import random
import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QCursor, QImage, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
                           QRegion)
from PySide6.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QTabBar, QWidget

SPREAD_MS = 7000       # wires -> controls -> screen -> eye -> glitch
REVEAL_MS = 1600       # the new screen shows through as the static clears
CELL = 4               # one static speckle is 4x4 screen pixels
_PALETTE = [(255, 36, 48), (170, 8, 20), (28, 0, 4), (255, 96, 74)]


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class UltronCorruption(QWidget):
    def __init__(self, window: QWidget, on_peak, on_finished=None):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._window = window
        self._on_peak = on_peak
        self._on_finished = on_finished
        self._pm = window.grab()                          # the old screen, taken before anything covers it
        self._sync()
        self._core_rect, self._control_rects = self._find_regions()
        w, h = max(8, (self.width() // CELL + 3) // 4 * 4), max(8, self.height() // CELL + 1)
        self._noise = [bytearray(os.urandom(w * h)) for _ in range(4)]      # four frames of random static
        self._imgs = [QImage(bytes(n), w, h, w, QImage.Format_Indexed8) for n in self._noise]
        self._t0 = time.monotonic()
        self._peaked = False
        self._reveal_t0 = 0.0
        self._done = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)
        self.show()
        self.raise_()

    # -- geometry -------------------------------------------------------------------------------
    def _sync(self) -> None:
        o = self._window.mapToGlobal(QPoint0)
        self.setGeometry(QRect(o, self._window.size()))

    def _find_regions(self):
        """The core (its rings and beams are the 'wires') and every control and tab, in this window's coordinates."""
        core = None
        try:
            c = self._window.ai_core
            core = QRect(c.mapTo(self._window, QPoint0), c.size()).adjusted(-10, -10, 10, 10)
        except Exception:
            pass
        rects = []
        try:
            for kind in (QAbstractButton, QTabBar, QComboBox, QLineEdit):
                for wd in self._window.findChildren(kind):
                    if wd.isVisible() and wd.width() > 4:
                        rects.append(QRect(wd.mapTo(self._window, QPoint0), wd.size()).adjusted(-4, -4, 4, 4))
        except Exception:
            pass
        return core, rects

    # -- timeline -------------------------------------------------------------------------------
    def _tick(self) -> None:
        try:
            if self._done:
                return
            self._sync()
            now = time.monotonic()
            if not self._peaked and (now - self._t0) * 1000.0 >= SPREAD_MS:
                self._peaked = True
                self._reveal_t0 = now
                try:
                    self._on_peak()                       # the real Ultron screen is built now, hidden behind the static
                except Exception:
                    self._finish()
                    return
            if self._peaked and (now - self._reveal_t0) * 1000.0 >= REVEAL_MS:
                self._finish()
                return
            self.update()
        except Exception:
            self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.hide()
        self.deleteLater()
        if self._on_finished:
            try:
                self._on_finished()
            except Exception:
                pass

    def abort(self) -> None:
        self._finish()

    # -- drawing --------------------------------------------------------------------------------
    def _static(self, p: QPainter, coverage: float, clip=None, frame: int = 0, alpha: float = 1.0) -> None:
        """Random red static over the clip area; coverage 0..1 is how much of it is filled in."""
        if coverage <= 0.002 or alpha <= 0:
            return
        img = self._imgs[frame % 4]
        t = int(255 * (1.0 - min(1.0, coverage)))
        table = []
        for i in range(256):
            if i < t:
                table.append(0)                                           # transparent speckle
            else:
                r, g, b = _PALETTE[i % 4]
                table.append((255 << 24) | (r << 16) | (g << 8) | b)
        img.setColorTable(table)
        p.save()
        if clip is not None:
            p.setClipRegion(clip)
        p.setOpacity(alpha)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(QRectF(0, 0, self.width(), self.height()), img)
        p.restore()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            self._paint(p)
        except Exception:
            self._finish()
        finally:
            p.end()

    def _paint(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        now = time.monotonic()
        frame = int(now * 14)
        rnd = random.Random(frame * 7919)
        reveal = 0.0
        if self._peaked:
            reveal = min(1.0, (now - self._reveal_t0) * 1000.0 / REVEAL_MS)
        prog = min(1.0, (now - self._t0) * 1000.0 / SPREAD_MS)
        veil = 1.0 - _smooth(reveal * 1.15)               # 1 while corrupting, fading to 0 as the new screen shows

        # the old screen, reddening as the corruption spreads; it fades out during the reveal
        if veil > 0:
            p.setOpacity(1.0 if reveal < 0.25 else max(0.0, 1.0 - (reveal - 0.25) / 0.5))
            p.drawPixmap(0, 0, self._pm)
            p.setOpacity(1.0)
            p.fillRect(0, 0, w, h, QColor(255, 20, 30, int(150 * _smooth(prog / 0.9) * veil)))

        # 1) the wires, 2) the controls and tabs, 3) the whole screen
        c1 = _smooth(prog / 0.28)
        c2 = _smooth((prog - 0.24) / 0.30)
        c3 = _smooth((prog - 0.52) / 0.30)
        fade = veil
        if self._core_rect is not None:
            self._static(p, c1 * 0.9, QRegion(self._core_rect), frame, fade)
        if self._control_rects:
            reg = QRegion()
            for r in self._control_rects:
                reg = reg.united(QRegion(r))
            self._static(p, c2 * 0.92, reg, frame + 1, fade)
        self._static(p, c3 * 0.85, None, frame + 2, fade)
        if prog > 0.82:                                     # nearly all red: a solid red-black base under the eye
            p.fillRect(0, 0, w, h, QColor(40, 0, 6, int(150 * _smooth((prog - 0.82) / 0.1) * fade)))
            self._static(p, 0.55, None, frame + 3, fade)

        # the eye that forms in the static and watches you
        eye_t = _smooth((prog - 0.74) / 0.14) * (1.0 - _smooth((reveal - 0.1) / 0.5))
        if eye_t > 0.01:
            self._draw_eye(p, eye_t, now, frame)

        # the glitch: the picture tears just before Ultron takes over, and for a moment after
        glitch = max(_smooth((prog - 0.90) / 0.1) if not self._peaked else max(0.0, 1.0 - reveal * 3.0), 0.0)
        if glitch > 0:
            for _ in range(int(4 + 22 * glitch)):
                y = rnd.random() * h
                bar = rnd.randint(2, int(6 + 40 * glitch))
                col = QColor(255, 40, 50, 230) if rnd.random() < 0.6 else QColor(0, 0, 0, 235)
                p.fillRect(int(rnd.uniform(-40, 40) * glitch), int(y), w, bar, col)
            if rnd.random() < 0.3 * glitch:
                p.fillRect(0, 0, w, h, QColor(255, 30, 40, int(110 * rnd.random())))
        if veil > 0:
            p.setOpacity(0.35 * veil)
            for y in range(0, h, 3):                          # scan lines
                p.fillRect(0, y, w, 1, QColor(0, 0, 0, 120))
            p.setOpacity(1.0)

    def _draw_eye(self, p: QPainter, t: float, now: float, frame: int) -> None:
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        ew = min(w * 0.58, h * 0.95)
        blink = 1.0
        ph = (now * 0.5) % 4.0                                # a slow blink every few seconds
        if ph < 0.22:
            blink = max(0.08, abs(ph - 0.11) / 0.11)
        eh = ew * 0.34 * blink * (0.6 + 0.4 * t)
        jitter = random.Random(frame * 131)
        p.save()
        p.setOpacity(t)
        eye = QPainterPath()
        eye.moveTo(cx - ew / 2, cy)
        eye.quadTo(cx, cy - eh * 1.9, cx + ew / 2, cy)
        eye.quadTo(cx, cy + eh * 1.9, cx - ew / 2, cy)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(14, 0, 2))
        p.drawPath(eye)
        p.setClipPath(eye)
        # the iris follows the mouse, so it seems to look at you
        m = self.mapFromGlobal(QCursor.pos())
        dx, dy = (m.x() - cx) / max(1.0, w / 2), (m.y() - cy) / max(1.0, h / 2)
        ir = eh * 0.95
        ic = QPointF(cx + max(-1.0, min(1.0, dx)) * ew * 0.16, cy + max(-1.0, min(1.0, dy)) * eh * 0.5)
        g = QRadialGradient(ic, ir)
        g.setColorAt(0.0, QColor(255, 70, 60))
        g.setColorAt(0.6, QColor(200, 20, 28))
        g.setColorAt(1.0, QColor(70, 0, 8))
        p.setBrush(QBrush(g))
        p.drawEllipse(ic, ir, ir)
        # the iris is made of static too
        iris = QPainterPath()
        iris.addEllipse(ic, ir, ir)
        p.setClipPath(iris)
        self._static(p, 0.45, None, frame, 0.9)
        p.setClipPath(eye)
        p.setBrush(QColor(8, 0, 2))
        p.drawEllipse(ic, ir * 0.38, ir * 0.38)               # the pupil
        p.setBrush(QColor(255, 210, 200, 220))
        p.drawEllipse(QPointF(ic.x() - ir * 0.16, ic.y() - ir * 0.2), ir * 0.07, ir * 0.07)   # a small glint
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 50, 60, 235), 4))
        p.translate(jitter.uniform(-2, 2), jitter.uniform(-1, 1))
        p.drawPath(eye)
        p.restore()


from PySide6.QtCore import QPoint as _QPoint  # noqa: E402

QPoint0 = _QPoint(0, 0)
