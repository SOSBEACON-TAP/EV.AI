"""Switching to Ultron: the real screen is taken over by a glitch, in four stages -
  1. the wires: thin glitch traces and torn slices around the AI core,
  2. the controls and tabs: their slices tear sideways, tinted dark red,
  3. the whole screen: it drains to a grayish red, tears and splits into colour fringes,
  4. a sentinel scanner (rings, a vertical slit that watches you) assembles out of the glitch,
then the picture tears one last time and the real Ultron screen shows through.

The colours are a mix of reds (crimson, blood, ember, ash, black), never one flat red, and there is no static: it is all
the actual screen being torn and recoloured. A see-through window of its own lies over the app, so a picture of the
app can be taken underneath it. It is only cosmetic: any error removes it and the switch still happens."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QTabBar, QWidget

SPREAD_MS = 6500       # wires -> controls -> screen -> sentinel -> tear
REVEAL_MS = 1500       # the new screen shows through as the glitch clears

# a mix of reds, from near-black to a hot ember, plus a pale flash
CRIMSON, BLOOD, MAROON = (204, 18, 48), (150, 10, 28), (76, 6, 18)
EMBER, ASH, VOID, PALE = (236, 76, 44), (128, 72, 76), (14, 2, 6), (255, 206, 196)
TINTS = [CRIMSON, BLOOD, EMBER, ASH, MAROON, CRIMSON]
ORIGIN = QPoint(0, 0)


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _col(rgb, a: int = 255) -> QColor:
    return QColor(rgb[0], rgb[1], rgb[2], max(0, min(255, int(a))))


def _channel(pm: QPixmap, rgb) -> QPixmap:
    """A copy of the picture keeping only one colour channel (for the colour-fringe split)."""
    out = QPixmap(pm)
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode_Multiply)
    p.fillRect(out.rect(), QColor(*rgb))
    p.end()
    return out


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
        img = self._pm.toImage()
        self._gray = QPixmap.fromImage(img.convertToFormat(QImage.Format_Grayscale8))
        self._r, self._g, self._b = _channel(self._pm, (255, 0, 0)), _channel(self._pm, (0, 255, 0)), _channel(self._pm, (0, 0, 255))
        self._sync()
        self._core_rect, self._control_rects = self._find_regions()
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
        o = self._window.mapToGlobal(ORIGIN)
        self.setGeometry(QRect(o, self._window.size()))

    def _find_regions(self):
        """The core (its rings and beams are the 'wires') and every control and tab, in this window's coordinates."""
        core = None
        try:
            c = self._window.ai_core
            core = QRect(c.mapTo(self._window, ORIGIN), c.size()).adjusted(-10, -10, 10, 10)
        except Exception:
            pass
        rects = []
        try:
            for kind in (QAbstractButton, QTabBar, QComboBox, QLineEdit):
                for wd in self._window.findChildren(kind):
                    if wd.isVisible() and wd.width() > 4:
                        rects.append(QRect(wd.mapTo(self._window, ORIGIN), wd.size()).adjusted(-4, -4, 4, 4))
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
                    self._on_peak()                       # the real Ultron screen is built now, hidden behind the glitch
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
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            self._paint(p)
        except Exception:
            self._finish()
        finally:
            p.end()

    def _tear(self, p: QPainter, rnd: random.Random, rects, count: int, shift: float, tall: int, src: QPixmap) -> None:
        """Slices of the screen torn sideways inside the given areas, each tinted with one of the reds."""
        if not rects or count <= 0:
            return
        W, H = self.width(), self.height()
        for _ in range(count):
            r = rects[rnd.randrange(len(rects))]
            hgt = rnd.randint(2, max(3, tall))
            y = r.top() + rnd.random() * max(1, r.height() - hgt)
            dx = rnd.uniform(-shift, shift)
            dest = QRectF(r.left() + dx, y, r.width(), hgt)
            p.drawPixmap(dest, src, QRectF(r.left(), y, r.width(), hgt))
            tint = TINTS[rnd.randrange(len(TINTS))]
            p.fillRect(dest, _col(tint, 70 + rnd.random() * 90))
            if rnd.random() < 0.16:                       # a thin bright flash on the tear
                p.fillRect(QRectF(dest.left(), y, dest.width(), 1.5), _col(PALE, 150))
        p.setOpacity(1.0)

    def _blocks(self, p: QPainter, rnd: random.Random, count: int, size: int, src: QPixmap) -> None:
        """Blocks of the screen copied to the wrong place, like a broken video frame."""
        W, H = self.width(), self.height()
        for _ in range(count):
            bw, bh = rnd.randint(size // 2, size * 2), rnd.randint(size // 3, size)
            sx, sy = rnd.random() * max(1, W - bw), rnd.random() * max(1, H - bh)
            dx, dy = sx + rnd.uniform(-size * 2, size * 2), sy + rnd.uniform(-size, size)
            dest = QRectF(dx, dy, bw, bh)
            p.drawPixmap(dest, src, QRectF(sx, sy, bw, bh))
            p.fillRect(dest, _col(TINTS[rnd.randrange(len(TINTS))], 80 + rnd.random() * 80))

    def _paint(self, p: QPainter) -> None:
        W, H = self.width(), self.height()
        now = time.monotonic()
        frame = int(now * 16)
        rnd = random.Random(frame * 7919)
        reveal = min(1.0, (now - self._reveal_t0) * 1000.0 / REVEAL_MS) if self._peaked else 0.0
        prog = min(1.0, (now - self._t0) * 1000.0 / SPREAD_MS)
        veil = 1.0 - _smooth(reveal * 1.1)               # 1 while the glitch holds, fading as the new screen shows through
        if veil <= 0:
            return
        p.setOpacity(veil)

        c1 = _smooth(prog / 0.26)                         # 1) wires
        c2 = _smooth((prog - 0.2) / 0.28)                 # 2) controls and tabs
        c3 = _smooth((prog - 0.46) / 0.3)                 # 3) the whole screen
        split = 7.0 * _smooth((prog - 0.3) / 0.4) + (10.0 * (1.0 - reveal) if prog > 0.92 else 0.0)

        # the screen itself, split into colour fringes once the glitch has spread
        if split > 0.4:
            p.fillRect(0, 0, W, H, _col(VOID))
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            s = int(split)
            p.drawPixmap(s, 0, self._r)
            p.drawPixmap(0, 0, self._g)
            p.drawPixmap(-s, 0, self._b)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        else:
            p.drawPixmap(0, 0, self._pm)

        # the screen drains to a grayish red, then darkens
        if c3 > 0.01:
            p.setOpacity(veil * 0.85 * c3)
            p.drawPixmap(0, 0, self._gray)
            p.setOpacity(veil)
            k = c3
            tone = (int(255 - (255 - 176) * k), int(255 - (255 - 96) * k), int(255 - (255 - 104) * k))
            p.setCompositionMode(QPainter.CompositionMode_Multiply)
            p.fillRect(0, 0, W, H, QColor(*tone))
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.fillRect(0, 0, W, H, _col(VOID, 150 * _smooth((prog - 0.7) / 0.25)))

        # 1) the wires: traces and tears around the core
        src = self._gray if c3 > 0.5 else self._pm
        if self._core_rect is not None:
            self._tear(p, rnd, [self._core_rect], int(3 + 16 * c1), 6 + 26 * c1, int(4 + 14 * c1), src)
            for _ in range(int(30 * c1)):                 # thin traces
                r = self._core_rect
                y = r.top() + rnd.random() * r.height()
                x0 = r.left() + rnd.random() * r.width() * 0.7
                p.fillRect(QRectF(x0, y, rnd.random() * r.width() * 0.6, 1.5), _col(TINTS[rnd.randrange(len(TINTS))], 190))
        # 2) the controls and tabs
        if self._control_rects:
            self._tear(p, rnd, self._control_rects, int(4 + 40 * c2), 8 + 40 * c2, int(5 + 12 * c2), src)
        # 3) the whole screen
        full = [QRect(0, 0, W, H)]
        self._tear(p, rnd, full, int(2 + 26 * c3), 10 + 70 * c3, int(6 + 30 * c3), src)
        self._blocks(p, rnd, int(14 * c3), max(24, W // 28), src)

        # a bright band sweeps down the screen
        if c3 > 0.05:
            y = (now * 520) % (H + 200) - 100
            p.fillRect(QRectF(0, y, W, 38), _col(CRIMSON, 34 * c3))
            p.fillRect(QRectF(0, y + 17, W, 2), _col(PALE, 70 * c3))

        # 4) the sentinel scanner assembles out of the glitch
        sent = _smooth((prog - 0.72) / 0.18) * (1.0 - _smooth((reveal - 0.1) / 0.5))
        if sent > 0.01:
            self._draw_sentinel(p, sent, now, rnd, veil)

        # the last tear: the picture breaks up just before Ultron takes over, and for a moment after
        glitch = _smooth((prog - 0.9) / 0.1) if not self._peaked else max(0.0, 1.0 - reveal * 2.6)
        if glitch > 0:
            self._tear(p, rnd, full, int(10 + 34 * glitch), 30 + 120 * glitch, int(8 + 50 * glitch), src)
            for _ in range(int(3 + 12 * glitch)):
                y = rnd.random() * H
                p.fillRect(QRectF(0, y, W, rnd.randint(1, 5)), _col(rnd.choice([VOID, CRIMSON, EMBER]), 215))
            if rnd.random() < 0.28 * glitch:
                p.fillRect(0, 0, W, H, _col(rnd.choice([CRIMSON, BLOOD]), 70 * rnd.random()))
        # scan lines over everything
        p.setOpacity(0.22 * veil)
        for y in range(0, H, 3):
            p.fillRect(0, y, W, 1, QColor(0, 0, 0, 140))
        p.setOpacity(1.0)

    def _draw_sentinel(self, p: QPainter, t: float, now: float, rnd: random.Random, veil: float) -> None:
        """Rings turning against each other and a vertical slit at the centre that follows your mouse. Drawn twice with
        a small offset in two reds, so it looks as if it is made of the glitch."""
        W, H = self.width(), self.height()
        cx, cy = W / 2.0, H / 2.0
        R = min(W, H) * 0.27 * (0.7 + 0.3 * t)
        m = self.mapFromGlobal(QCursor.pos())
        lx = max(-1.0, min(1.0, (m.x() - cx) / max(1.0, W / 2.0)))
        ly = max(-1.0, min(1.0, (m.y() - cy) / max(1.0, H / 2.0)))
        spin = now * 40.0
        jitter = rnd.uniform(-3, 3) if rnd.random() < 0.35 else 0.0
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        # dark disc so the scanner reads clearly over the busy screen
        disc = QRadialGradient(QPointF(cx, cy), R * 1.25)
        disc.setColorAt(0.0, _col(VOID, 235 * t))
        disc.setColorAt(0.8, _col(MAROON, 190 * t))
        disc.setColorAt(1.0, _col(VOID, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(disc)
        p.drawEllipse(QPointF(cx, cy), R * 1.25, R * 1.25)
        for ox, tone in ((jitter + 3.0, BLOOD), (jitter - 2.0, EMBER), (jitter, CRIMSON)):
            p.save()
            p.translate(ox, 0)
            alpha = (120 if tone is not CRIMSON else 235) * t
            # outer ring with tick marks
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(_col(tone, alpha * 0.55), 1.6))
            p.drawEllipse(QPointF(cx, cy), R * 1.12, R * 1.12)
            for i in range(72):
                a = math.radians(i * 5.0 + spin * 0.15)
                ln = R * (0.06 if i % 6 == 0 else 0.03)
                p.drawLine(QPointF(cx + math.cos(a) * R * 1.12, cy + math.sin(a) * R * 1.12),
                           QPointF(cx + math.cos(a) * (R * 1.12 - ln), cy + math.sin(a) * (R * 1.12 - ln)))
            # three rings of arcs turning against each other
            for ring, (rad, segs, width, speed) in enumerate(((1.0, 12, 7, 1.0), (0.78, 9, 5, -1.6), (0.56, 6, 4, 2.2))):
                p.setPen(QPen(_col(tone, alpha), width, Qt.SolidLine, Qt.FlatCap))
                span = 360.0 / segs
                shown = max(0, min(segs, int(segs * _smooth(t * 1.3 - ring * 0.12) + 0.999)))
                rect = QRectF(cx - R * rad, cy - R * rad, R * rad * 2, R * rad * 2)
                for i in range(shown):
                    a0 = i * span + spin * speed
                    p.drawArc(rect, int(-a0 * 16), int(-(span * 0.62) * 16))
            p.restore()
        # crosshair ticks
        p.setPen(QPen(_col(PALE, 150 * t), 1.5))
        for a in (0, 90, 180, 270):
            ar = math.radians(a)
            p.drawLine(QPointF(cx + math.cos(ar) * R * 1.2, cy + math.sin(ar) * R * 1.2),
                       QPointF(cx + math.cos(ar) * R * 1.36, cy + math.sin(ar) * R * 1.36))
        # the core: a glow with a vertical slit that follows the mouse and tightens now and then
        gx, gy = cx + lx * R * 0.12, cy + ly * R * 0.12
        glow = QRadialGradient(QPointF(gx, gy), R * 0.5)
        glow.setColorAt(0.0, _col(EMBER, 230 * t))
        glow.setColorAt(0.45, _col(CRIMSON, 120 * t))
        glow.setColorAt(1.0, _col(CRIMSON, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(gx, gy), R * 0.5, R * 0.5)
        squeeze = 0.55 + 0.45 * abs(math.sin(now * 0.9))
        slit = QPainterPath()
        sw, sh = R * 0.07 * squeeze, R * 0.36
        slit.moveTo(gx, gy - sh)
        slit.quadTo(gx + sw * 2.2, gy, gx, gy + sh)
        slit.quadTo(gx - sw * 2.2, gy, gx, gy - sh)
        p.setBrush(_col(VOID, 245 * t))
        p.drawPath(slit)
        p.setPen(QPen(_col(PALE, 235 * t), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawPath(slit)
        p.restore()
