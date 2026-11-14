"""The mode picker: a ring of twelve chips around an arc-reactor core. Each chip is one mode of EV AI, drawn as a small
circuit board with the name on a label (like the FRIDAY chip). Click a chip to switch to that mode; click the glowing
core for Overdrive. Choosing Ultron corrupts its chip and the wheel before the screen turns red."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontInfo, QFontMetricsF, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QDialog, QToolTip

from ui.chip_art import chip_layout

SLOTS = 12
CHIP_W, CHIP_H = 60.0, 80.0
RING_R = 172          # distance of the chips from the centre
SCALE = 4             # chips are drawn at 4x and shrunk, so every trace stays crisp

# (bright colour, dark colour) of each mode's chip when it is lit
THEMES = {
    "ev": ((60, 160, 245), (12, 60, 150)), "jarvis": ((240, 180, 50), (125, 72, 6)),
    "ultron": ((235, 50, 55), (100, 10, 16)), "game": ((55, 215, 120), (10, 92, 52)),
    "karen": ((170, 100, 240), (72, 30, 132)), "friday": ((215, 100, 225), (84, 30, 104)),
    "tars": ((190, 198, 208), (62, 68, 80)), "gideon": ((70, 205, 235), (10, 92, 122)),
    "edith": ((90, 165, 255), (20, 62, 152)), "sonar": ((45, 205, 185), (10, 92, 82)),
    "minority": ((245, 100, 175), (112, 22, 72)), "baymax": ((255, 128, 116), (132, 42, 42)),
}
_BLUE = THEMES["ev"]

DESCRIPTIONS = {
    "ev": "EV: your everyday assistant, and control of this computer from your phone",
    "jarvis": "Jarvis: watches your PC's health, battery and speed",
    "ultron": "Ultron: security tools, the radar, and a terminal that writes and runs code",
    "game": "Game: boost the PC, auto-clicker, game stats and break reminders",
    "karen": "Karen: screen-time limits and blocking distracting sites",
    "friday": "Friday: quick, automatic answers",
    "tars": "Tars: serious and to the point",
    "gideon": "Gideon: slow, deep thinking",
    "edith": "Edith: click her glasses to start the HUD",
    "sonar": "Sonar: the sound player",
    "minority": "Minority: the video player you control with gestures",
    "baymax": "Baymax: a gentle health companion",
}


class ModePicker(QDialog):
    chosen = Signal(str)

    def __init__(self, parent, modes: list[tuple[str, str]], active: set[str]):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setMouseTracking(True)
        self.resize(560, 560)
        self._modes = modes[:SLOTS]
        self._active = set(active)
        self._hover = -1
        self._core_hover = False
        self._spin = 0.0
        self._chips: dict[tuple[str, bool], QPixmap] = {}
        self._corrupt_t0: float | None = None        # set when Ultron was chosen: the wheel corrupts, then closes
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def done(self, result: int) -> None:
        self._timer.stop()
        super().done(result)

    # -- geometry -------------------------------------------------------------------------------
    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _in_core(self, pos) -> bool:
        c = self._center()
        return math.hypot(pos.x() - c.x(), pos.y() - c.y()) < 100

    def _slot_at(self, pos) -> int:
        c = self._center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        dist = math.hypot(dx, dy)
        if dist < 120 or dist > 232:
            return -1
        ang = math.degrees(math.atan2(dx, -dy)) % 360      # clockwise from the top
        return int(((ang + 360 / SLOTS / 2) % 360) // (360 / SLOTS))

    def _chip_center(self, i: int) -> QPointF:
        c = self._center()
        a = math.radians(i * 360 / SLOTS)
        return QPointF(c.x() + RING_R * math.sin(a), c.y() - RING_R * math.cos(a))

    # -- animation ------------------------------------------------------------------------------
    def _tick(self) -> None:
        self._spin = (self._spin + 0.8) % 360
        if self._corrupt_t0 is not None and time.monotonic() - self._corrupt_t0 >= 0.95:
            self._timer.stop()
            self._corrupt_t0 = None
            self.chosen.emit("ultron")
            self.accept()
            return
        self.update()

    # -- input ----------------------------------------------------------------------------------
    def mouseMoveEvent(self, e) -> None:
        if self._corrupt_t0 is not None:
            return
        i = self._slot_at(e.position())
        core = self._in_core(e.position())
        if i != self._hover or core != self._core_hover:
            self._hover, self._core_hover = i, core
            self.setCursor(Qt.PointingHandCursor if (0 <= i < len(self._modes) or core) else Qt.ArrowCursor)
            tip = ("Overdrive: every important tool at once, for 1 minute 30 seconds" if core
                   else (DESCRIPTIONS.get(self._modes[i][0], "") + f"  (press {self._key_for(i)})") if 0 <= i < len(self._modes) else "")
            if tip:
                QToolTip.showText(e.globalPosition().toPoint(), tip, self)
            else:
                QToolTip.hideText()

    def mousePressEvent(self, e) -> None:
        if self._corrupt_t0 is not None:
            return
        i = self._slot_at(e.position())
        if self._in_core(e.position()):                     # the glowing centre: Overdrive (90 seconds)
            self.chosen.emit("overdrive")
            self.accept()
        elif 0 <= i < len(self._modes):
            if self._modes[i][0] == "ultron" and "ultron" not in self._active:
                self._hover = i
                self._corrupt_t0 = time.monotonic()         # Ultron: the chip corrupts first
            else:
                self.chosen.emit(self._modes[i][0])
                self.accept()
        elif math.hypot(e.position().x() - self._center().x(), e.position().y() - self._center().y()) > 270:
            self.reject()

    @staticmethod
    def _key_for(i: int) -> str:
        return str((i + 1) % 10) if i < 10 else "-"

    def keyPressEvent(self, e) -> None:
        if self._corrupt_t0 is not None:
            return
        k = e.key()
        slot = -1
        if Qt.Key_1 <= k <= Qt.Key_9:
            slot = k - Qt.Key_1
        elif k == Qt.Key_0:
            slot = 9
        elif k == Qt.Key_Minus:
            slot = 10
        elif k == Qt.Key_Equal:
            slot = 11
        if 0 <= slot < len(self._modes):                       # number keys pick a chip: 1 = the first ... 0 = the tenth
            key = self._modes[slot][0]
            if key == "ultron" and "ultron" not in self._active:
                self._hover = slot
                self._corrupt_t0 = time.monotonic()
            else:
                self.chosen.emit(key)
                self.accept()
            return
        if k == Qt.Key_O:                                      # O = Overdrive
            self.chosen.emit("overdrive")
            self.accept()
            return
        if e.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(e)

    # -- chip artwork ---------------------------------------------------------------------------
    def _chip_pixmap(self, key: str, lit: bool) -> QPixmap:
        """A chip drawn once (at 4x) and kept: dark case with gold pins, white label strip, and a circuit board of
        copper traces. Lit chips use the mode's own colour; the others are blue."""
        k = (key, lit)
        if k in self._chips:
            return self._chips[k]
        bright, dark = THEMES.get(key, _BLUE) if lit else _BLUE
        m = 3.0
        cw, ch = CHIP_W + 2 * m, CHIP_H
        pm = QPixmap(int(cw * SCALE), int(ch * SCALE))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(SCALE, SCALE)
        case = QRectF(m, 0.5, CHIP_W, CHIP_H - 1)
        # gold pins along both sides
        p.setPen(Qt.NoPen)
        for y in range(18, int(CHIP_H) - 8, 6):
            for x in (0.6, m + CHIP_W - 0.6):
                g = QLinearGradient(x, y, x + m, y)
                g.setColorAt(0, QColor(250, 215, 120))
                g.setColorAt(1, QColor(170, 125, 40))
                p.setBrush(QBrush(g))
                p.drawRoundedRect(QRectF(x, y, m, 3.4), 0.8, 0.8)
        # black case with a metallic sheen
        g = QLinearGradient(case.topLeft(), case.bottomRight())
        g.setColorAt(0.0, QColor(52, 60, 76))
        g.setColorAt(0.45, QColor(16, 20, 30))
        g.setColorAt(1.0, QColor(8, 10, 16))
        p.setPen(QPen(QColor(*bright).lighter(130) if lit else QColor(96, 112, 134), 0.9))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(case, 7, 7)
        # white label strip
        strip = QRectF(case.left() + 3, case.top() + 3, CHIP_W - 6, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(247, 249, 251))
        p.drawRoundedRect(strip, 2.5, 2.5)
        # the circuit board
        panel = QRectF(case.left() + 3, strip.bottom() + 3, CHIP_W - 6, case.bottom() - strip.bottom() - 6)
        bg = QLinearGradient(panel.topLeft(), panel.bottomLeft())
        bg.setColorAt(0.0, QColor(*bright).lighter(112))
        bg.setColorAt(1.0, QColor(*dark))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(panel, 3, 3)
        p.save()
        p.setClipRect(panel)
        p.translate(panel.topLeft())
        seed = sum(ord(ch_) * (n + 3) for n, ch_ in enumerate(key)) + 11
        lines, nodes = chip_layout(seed, panel.width(), panel.height())
        trace = QColor(240, 250, 255, 235)
        p.setPen(QPen(trace, 0.55, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        for line in lines:
            path = QPainterPath(QPointF(*line[0]))
            for pt in line[1:]:
                path.lineTo(QPointF(*pt))
            p.drawPath(path)
        for x, y, hollow in nodes:
            if hollow:
                p.setPen(QPen(trace, 0.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(x, y), 1.05, 1.05)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(trace)
                p.drawEllipse(QPointF(x, y), 0.8, 0.8)
        p.restore()
        # glossy highlight across the top-left of the case
        hl = QLinearGradient(case.topLeft(), QPointF(case.left() + 30, case.top() + 40))
        hl.setColorAt(0.0, QColor(255, 255, 255, 40))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(hl))
        p.drawRoundedRect(case, 7, 7)
        p.end()
        pm.setDevicePixelRatio(SCALE)
        self._chips[k] = pm
        return pm

    def _draw_chip(self, p: QPainter, i: int) -> None:
        used = i < len(self._modes)
        key, label = self._modes[i] if used else ("", "")
        active = used and key in self._active
        hot = used and i == self._hover
        lit = active or hot
        c = self._chip_center(i)
        ct = 0.0 if self._corrupt_t0 is None else min(1.0, (time.monotonic() - self._corrupt_t0) / 0.9)
        corrupting = used and key == "ultron" and self._corrupt_t0 is not None
        if not used:
            p.setOpacity(0.28)
        elif self._corrupt_t0 is not None and not corrupting:
            p.setOpacity(max(0.15, 1.0 - ct))                       # everything else dims while Ultron takes over
        if lit and not corrupting:                                  # soft glow behind a lit chip
            bright = THEMES.get(key, _BLUE)[0]
            g = QRadialGradient(c, 52)
            g.setColorAt(0.0, QColor(*bright, 120))
            g.setColorAt(1.0, QColor(*bright, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(c, 52, 52)
        pm = self._chip_pixmap(key or "ev", lit or corrupting)
        w, h = pm.width() / SCALE, pm.height() / SCALE
        x0, y0 = c.x() - w / 2, c.y() - h / 2
        if corrupting:                                              # Ultron's chip tears, jitters and bleeds red
            import random
            rnd = random.Random(int(time.monotonic() * 30))
            for dx, dy, op in ((-5, 1, 0.55), (6, -1, 0.55), (0, 0, 1.0)):
                p.setOpacity(op * (0.6 + 0.4 * rnd.random()))
                p.drawPixmap(QPointF(x0 + dx * ct * 2 + rnd.uniform(-3, 3) * ct, y0 + dy + rnd.uniform(-2, 2) * ct), pm)
            p.setOpacity(1.0)
            for _ in range(int(3 + 9 * ct)):                         # corruption bars across the chip
                by = y0 + rnd.random() * h
                p.fillRect(QRectF(x0 - 6, by, w + 12, rnd.uniform(1.5, 6)),
                           QColor(255, 30, 40, 200) if rnd.random() < 0.65 else QColor(0, 0, 0, 220))
            p.fillRect(QRectF(x0, y0, w, h), QColor(255, 20, 30, int(120 * ct)))
        else:
            p.drawPixmap(QPointF(x0, y0), pm)
        # the name, written on the label
        if used:
            strip = QRectF(c.x() - CHIP_W / 2 + 3, c.y() - CHIP_H / 2 + 3.5, CHIP_W - 6, 16)
            f = QFont("Segoe Print", 8)
            if not QFontInfo(f).exactMatch():
                f = QFont("Segoe UI", 8)
                f.setBold(True)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
            size = 8.0
            fm = QFontMetricsF(f)
            while size > 5 and fm.horizontalAdvance(label) > strip.width() - 4:
                size -= 0.5
                f.setPointSizeF(size)
                fm = QFontMetricsF(f)
            p.setFont(f)
            p.setPen(QColor(10, 20, 40) if not corrupting else QColor(180, 10, 20))
            p.drawText(strip, Qt.AlignCenter, label)
        p.setOpacity(1.0)

    # -- the arc-reactor core -------------------------------------------------------------------
    def _draw_core(self, p: QPainter, c: QPointF, red: float) -> None:
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 2.4)
        od = self._core_hover or "overdrive" in self._active
        glow = (255, 150, 30) if od else (90, 215, 255)
        if red:
            glow = (int(glow[0] + (255 - glow[0]) * red), int(glow[1] * (1 - red) + 30 * red), int(glow[2] * (1 - red) + 40 * red))
        # housing
        p.setPen(QPen(QColor(150, 160, 175), 3))
        p.setBrush(QColor(5, 11, 20))
        p.drawEllipse(c, 116, 116)
        # fine ticks around the edge
        p.setPen(QPen(QColor(*glow, 170), 1.2))
        for n in range(72):
            a = math.radians(n * 5 - self._spin * 0.4)
            r1, r2 = 108, 112 if n % 6 else 114
            p.drawLine(QPointF(c.x() + r1 * math.cos(a), c.y() + r1 * math.sin(a)), QPointF(c.x() + r2 * math.cos(a), c.y() + r2 * math.sin(a)))
        # ten coil segments (copper windings on a dark ring), turning slowly like a reactor
        for n in range(10):
            a0 = n * 36 + self._spin * 0.25
            path = QPainterPath()
            rect_o, rect_i = QRectF(c.x() - 98, c.y() - 98, 196, 196), QRectF(c.x() - 66, c.y() - 66, 132, 132)
            path.arcMoveTo(rect_o, -a0)
            path.arcTo(rect_o, -a0, -26)
            path.arcTo(rect_i, -a0 - 26, 26)
            path.closeSubpath()
            g = QRadialGradient(c, 98)
            g.setColorAt(0.62, QColor(28, 40, 56))
            g.setColorAt(1.0, QColor(54, 70, 92))
            p.setPen(QPen(QColor(*glow, 200), 1.3))
            p.setBrush(QBrush(g))
            p.drawPath(path)
            p.setPen(QPen(QColor(214, 128, 52, 210), 0.8))             # the copper windings
            for k in range(1, 6):
                r = 66 + k * 5.2
                p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), int((-a0 - 3) * 16), int(-20 * 16))
        # glowing ring and core
        p.setPen(QPen(QColor(*glow, 230), 2.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, 60, 60)
        g = QRadialGradient(c, 58)
        g.setColorAt(0.0, QColor(255, 255, 255, 255))
        g.setColorAt(0.35, QColor(*glow, int(210 + 45 * pulse)))
        g.setColorAt(1.0, QColor(*glow, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, 58, 58)
        # the triangle in the middle, turning the other way
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.4))
        p.setBrush(Qt.NoBrush)
        tri = QPainterPath()
        for n in range(3):
            a = math.radians(-90 + n * 120 - self._spin * 0.6)
            pt = QPointF(c.x() + 32 * math.cos(a), c.y() + 32 * math.sin(a))
            tri.moveTo(pt) if n == 0 else tri.lineTo(pt)
        tri.closeSubpath()
        p.drawPath(tri)
        name = "SELECT MODE"
        if od:
            name = "OVERDRIVE"
        elif 0 <= self._hover < len(self._modes):
            name = self._modes[self._hover][1]
        else:
            on = [label for k, label in self._modes if k in self._active]
            if len(on) == 1:
                name = on[0]
            elif on:
                name = f"{len(on)} ON"
        f2 = QFont("Segoe UI", 9)
        f2.setBold(True)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f2)
        p.setPen(QColor(6, 24, 48))
        p.drawText(QRectF(c.x() - 52, c.y() - 11, 104, 22), Qt.AlignCenter, name)
        if name == "OVERDRIVE":
            p.setFont(QFont("Segoe UI", 6))
            p.drawText(QRectF(c.x() - 52, c.y() + 7, 104, 12), Qt.AlignCenter, "90 SECONDS")

    # -- drawing --------------------------------------------------------------------------------
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        c = self._center()
        ct = 0.0 if self._corrupt_t0 is None else min(1.0, (time.monotonic() - self._corrupt_t0) / 0.9)
        p.setPen(QPen(QColor(int(120 + 135 * ct), int(200 - 150 * ct), int(255 - 205 * ct), 90), 1.5))
        p.setBrush(QColor(int(6 + 30 * ct), int(10 - 6 * ct), int(18 - 10 * ct), 240))
        p.drawEllipse(c, 272, 272)
        # silver ring (it reddens when Ultron takes over)
        rc = QColor(int(168 + 40 * ct), int(176 - 130 * ct), int(188 - 140 * ct))
        p.setPen(QPen(rc, 16))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, 246, 246)
        p.setPen(QPen(QColor(235, 240, 248, 150), 2))
        p.drawEllipse(c, 254, 254)
        p.setPen(QPen(QColor(60, 66, 78), 2))
        p.drawEllipse(c, 237, 237)
        for i in range(SLOTS):
            self._draw_chip(p, i)
        self._draw_core(p, c, ct)
        if ct > 0:                                                  # the whole wheel flickers and tears
            import random
            rnd = random.Random(int(time.monotonic() * 25))
            for _ in range(int(2 + 10 * ct)):
                y = c.y() - 272 + rnd.random() * 544
                p.fillRect(QRectF(c.x() - 272, y, 544, rnd.uniform(1, 5)),
                           QColor(255, 30, 40, int(80 + 100 * ct)) if rnd.random() < 0.6 else QColor(0, 0, 0, 180))
        p.end()
