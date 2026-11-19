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
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
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
        self.setMinimumHeight(250)
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

    # -- drawing ---------------------------------------------------------------------------------------------
    def _body_path(self) -> QPainterPath:
        p = QPainterPath()
        p.addEllipse(QRectF(40, 5, 20, 24))                                  # head
        p.addRoundedRect(QRectF(46, 29, 8, 8), 2, 2)                         # neck
        p.addRoundedRect(QRectF(31, 37, 38, 42), 8, 8)                       # torso
        p.addRoundedRect(QRectF(33, 76, 34, 36), 8, 8)                       # hips
        p.addRoundedRect(QRectF(11, 40, 15, 70), 7, 7)                       # arms
        p.addRoundedRect(QRectF(74, 40, 15, 70), 7, 7)
        p.addRoundedRect(QRectF(34, 110, 14, 84), 7, 7)                      # legs
        p.addRoundedRect(QRectF(52, 110, 14, 84), 7, 7)
        return p

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, ox, oy = self._map()
        p.save()
        p.translate(ox, oy)
        p.scale(s, s)

        # glow + outline
        body = self._body_path()
        pulse = 0.5 + 0.5 * math.sin(self._t * 2.2)
        for w, a in ((5.0, 22), (3.0, 40)):
            g = QColor(GLOW)
            g.setAlpha(int(a + 14 * pulse))
            p.setPen(QPen(g, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(body)
        p.setPen(QPen(LINE, 1.1))
        p.setBrush(QBrush(QColor(255, 90, 90, 18)))
        p.drawPath(body)

        # selectable zones
        for name, r in ZONES.items():
            hot = name == self._hover
            picked = name == self._picked
            if hot or picked:
                c = QColor(255, 140, 140, 90 if hot else 60)
                p.setPen(QPen(LINE, 0.9, Qt.DashLine))
                p.setBrush(QBrush(c))
                p.drawRoundedRect(r, 5, 5)
            else:
                p.setPen(QPen(DIM, 0.5, Qt.DotLine))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r, 5, 5)

        # heart
        hb = 1.0 + 0.18 * max(0.0, math.sin(self._t * 6.0)) ** 3
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 80, 80, 200))
        p.drawEllipse(QPointF(56, 50), 3.2 * hb, 3.2 * hb)

        # scan line sweeping down the body
        y = 4 + ((self._t * 38) % 196)
        grad = QColor(255, 150, 150, 120)
        p.setPen(QPen(grad, 1.2))
        p.drawLine(QPointF(6, y), QPointF(94, y))
        p.restore()

        # heartbeat trace along the bottom
        h = self.height()
        path = QPainterPath()
        w = self.width()
        base = h - 12
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
        p.setPen(QColor(255, 150, 150))
        label = (self._hover or self._picked or "touch where you feel something").upper()
        p.drawText(QRectF(0, 0, w, 12), Qt.AlignHCenter | Qt.AlignTop, label)
        p.end()
