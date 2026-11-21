"""
ui/body_hud.py
----------------
Baymax's human-body HUD: a glowing body outline with a scan line sweeping down it and a heartbeat trace.
Click a part of the body to tell Baymax where you feel something. It is only a pointer for your question:
nothing here measures your body or diagnoses anything.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

LINE = QColor(255, 120, 120)          # Baymax care red
GLOW = QColor(255, 90, 90)
DIM = QColor(255, 120, 120, 70)

# zone name -> rectangle in a 100 x 200 body space
ZONES = {
    "head": QRectF(38, 4, 24, 28),
    "chest": QRectF(31, 40, 38, 36),
    "stomach": QRectF(33, 76, 34, 34),
    "left arm": QRectF(8, 40, 20, 72),
    "right arm": QRectF(72, 40, 20, 72),
    "left leg": QRectF(33, 112, 17, 84),
    "right leg": QRectF(50, 112, 17, 84),
}


class BodyHud(QWidget):
    zone_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(340)
        self.setMouseTracking(True)
        self._t = 0.0
        self._hover: str | None = None
        self._picked: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    # -- animation only runs while the HUD is on screen ------------------------------------------------------
    def showEvent(self, e):
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def _tick(self):
        self._t += 0.04
        self.update()

    # -- geometry --------------------------------------------------------------------------------------------
    def _map(self):
        """(scale, x offset, y offset) that fit the 100 x 200 body space into the widget."""
        s = min(self.width() / 100.0, (self.height() - 28) / 200.0)
        return s, (self.width() - 100 * s) / 2.0, 6.0

    def _zone_at(self, pos) -> str | None:
        s, ox, oy = self._map()
        x, y = (pos.x() - ox) / s, (pos.y() - oy) / s
        for name, r in ZONES.items():
            if r.contains(x, y):
                return name
        return None

    def mouseMoveEvent(self, e):
        z = self._zone_at(e.position())
        if z != self._hover:
            self._hover = z
            self.setCursor(Qt.PointingHandCursor if z else Qt.ArrowCursor)

    def leaveEvent(self, e):
        self._hover = None

    def mousePressEvent(self, e):
        z = self._zone_at(e.position())
        if z:
            self._picked = z
            self.zone_clicked.emit(z)

    # -- drawing: a glowing blue body with a red skeleton inside, like an X-ray scan --------------------------------
    @staticmethod
    def _poly(pts) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(*pts[0])
        for pt in pts[1:]:
            path.lineTo(*pt)
        path.closeSubpath()
        return path

    def _body_path(self) -> QPainterPath:
        P = self._poly
        body = QPainterPath()
        body.addEllipse(QRectF(41, 3, 18, 24))                                                   # head
        for part in (
            P([(46, 24), (54, 24), (55, 36), (45, 36)]),                                          # neck
            P([(46, 34), (54, 34), (71, 38), (75, 44), (68, 64), (66, 96), (69, 112), (31, 112), (34, 96), (32, 64), (25, 44), (29, 38)]),  # torso
            P([(28, 38), (22, 40), (19, 70), (17, 100), (20, 112), (26, 112), (27, 100), (30, 70), (33, 44)]),   # left arm
            P([(72, 38), (78, 40), (81, 70), (83, 100), (80, 112), (74, 112), (73, 100), (70, 70), (67, 44)]),   # right arm
            P([(33, 108), (50, 108), (50, 150), (47, 192), (39, 192), (37, 150)]),                # left leg
            P([(67, 108), (50, 108), (50, 150), (53, 192), (61, 192), (63, 150)]),                # right leg
        ):
            body = body.united(part)
        return body

    def _draw_skeleton(self, p: QPainter, pulse: float) -> None:
        bone = QColor(255, 92, 104, 235)
        core = QColor(255, 190, 190, 235)

        def line(x1, y1, x2, y2, w=1.4):
            p.setPen(QPen(bone, w, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            p.setPen(QPen(core, w * 0.35, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        def mirror(fn, *a):
            fn(*a)
            fn(*(100 - v if i % 2 == 0 else v for i, v in enumerate(a)))

        p.setBrush(Qt.NoBrush)
        # skull, eye sockets, jaw
        p.setPen(QPen(bone, 1.3))
        p.drawEllipse(QRectF(43, 5, 14, 15))
        p.setBrush(QColor(20, 4, 8, 220))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(45.2, 11, 3.6, 3.6))
        p.drawEllipse(QRectF(51.2, 11, 3.6, 3.6))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(bone, 1.2))
        p.drawArc(QRectF(44, 14, 12, 12), 200 * 16, 140 * 16)
        # spine
        for i in range(24):
            y = 27 + i * 3.4
            p.setPen(QPen(bone, 0.9))
            p.setBrush(QColor(255, 120, 130, 120))
            w = 3.0 + (1.2 if 6 < i < 17 else 0.0)
            p.drawRoundedRect(QRectF(50 - w / 2, y, w, 2.4), 0.9, 0.9)
        p.setBrush(Qt.NoBrush)
        # ribcage: seven pairs of curved ribs, plus the breastbone
        for i in range(7):
            y = 38 + i * 4.6
            reach = 15.5 - abs(i - 2.5) * 0.9
            for sgn in (-1, 1):
                path = QPainterPath()
                path.moveTo(50 + sgn * 2, y)
                path.cubicTo(50 + sgn * reach * 0.9, y - 2.5, 50 + sgn * reach * 1.05, y + 5, 50 + sgn * 3.2, y + 8)
                p.setPen(QPen(bone, 1.1))
                p.drawPath(path)
        line(50, 38, 50, 66, 1.6)
        # shoulders, collarbones, arms
        mirror(line, 49, 36.5, 30, 38.5)
        p.setBrush(QColor(255, 120, 130, 140))
        p.setPen(QPen(bone, 1.0))
        for x in (27.5, 72.5):
            p.drawEllipse(QPointF(x, 40.5), 2.6, 2.6)
        p.setBrush(Qt.NoBrush)
        mirror(line, 27.5, 43, 24, 73)                    # upper arm
        mirror(line, 24, 75, 20.5, 104, 1.1)              # forearm
        mirror(line, 25.5, 75, 23.5, 104, 1.0)
        p.setPen(QPen(bone, 1.0))
        for x in (20.5, 79.5):
            p.drawEllipse(QRectF(x - 2.6, 104, 5.2, 7))   # hands
        # pelvis
        p.setPen(QPen(bone, 1.3))
        p.setBrush(QColor(255, 120, 130, 90))
        p.drawEllipse(QRectF(36, 97, 14, 13))
        p.drawEllipse(QRectF(50, 97, 14, 13))
        p.setBrush(Qt.NoBrush)
        # legs
        mirror(line, 42, 112, 41, 149, 1.7)               # thigh bones
        p.setPen(QPen(bone, 1.0))
        p.setBrush(QColor(255, 120, 130, 140))
        for x in (41, 59):
            p.drawEllipse(QPointF(x, 151), 2.4, 2.4)       # knees
        p.setBrush(Qt.NoBrush)
        mirror(line, 41, 154, 41.5, 188, 1.5)             # shin
        p.setPen(QPen(bone, 1.0))
        for x in (41.5, 58.5):
            p.drawEllipse(QRectF(x - 4, 188, 8, 4.5))      # feet

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, ox, oy = self._map()
        p.save()
        p.translate(ox, oy)
        p.scale(s, s)
        pulse = 0.5 + 0.5 * math.sin(self._t * 2.2)

        # glowing blue body
        body = self._body_path()
        for w, a in ((7.0, 18), (4.5, 30), (2.6, 55)):
            g = QColor(70, 150, 255, int(a + 14 * pulse))
            p.setPen(QPen(g, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(body)
        grad = QLinearGradient(0, 0, 0, 200)
        grad.setColorAt(0.0, QColor(60, 140, 255, 70))
        grad.setColorAt(1.0, QColor(30, 80, 190, 40))
        p.setPen(QPen(QColor(120, 190, 255, 230), 1.1))
        p.setBrush(QBrush(grad))
        p.drawPath(body)

        self._draw_skeleton(p, pulse)

        # the selectable zones
        for name, r in ZONES.items():
            hot, picked = name == self._hover, name == self._picked
            if hot or picked:
                p.setPen(QPen(LINE, 0.9, Qt.DashLine))
                p.setBrush(QBrush(QColor(255, 140, 140, 70 if hot else 45)))
                p.drawRoundedRect(r, 5, 5)

        # heart glow
        hb = 1.0 + 0.2 * max(0.0, math.sin(self._t * 6.0)) ** 3
        rg = QRadialGradient(QPointF(56, 52), 7 * hb)
        rg.setColorAt(0.0, QColor(255, 120, 120, 230))
        rg.setColorAt(1.0, QColor(255, 60, 60, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(56, 52), 7 * hb, 7 * hb)

        # scan band sweeping down the body
        y = 2 + ((self._t * 34) % 198)
        band = QLinearGradient(0, y - 6, 0, y + 6)
        band.setColorAt(0.0, QColor(120, 200, 255, 0))
        band.setColorAt(0.5, QColor(150, 215, 255, 120))
        band.setColorAt(1.0, QColor(120, 200, 255, 0))
        p.setBrush(QBrush(band))
        p.drawRect(QRectF(4, y - 6, 92, 12))
        p.restore()

        # heartbeat trace along the bottom
        w, h = self.width(), self.height()
        path = QPainterPath()
        base = h - 10
        for i in range(0, int(w) + 1, 2):
            ph = (i / w * 3.0 - self._t * 0.9) % 1.0
            y2 = base
            if 0.42 < ph < 0.46:
                y2 = base - 9
            elif 0.46 <= ph < 0.5:
                y2 = base + 6
            path.lineTo(i, y2) if i else path.moveTo(i, y2)
        p.setPen(QPen(QColor(255, 110, 110, 190), 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        f = QFont()
        f.setPointSize(7)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(150, 205, 255))
        label = (self._hover or self._picked or "touch where you feel something").upper()
        p.drawText(QRectF(0, 0, w, 12), Qt.AlignHCenter | Qt.AlignTop, label)
        p.end()
