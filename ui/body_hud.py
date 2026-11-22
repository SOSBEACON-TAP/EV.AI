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

# zone name -> (left, top, right, bottom) as fractions of the X-ray picture
ZONES = {
    "head": (0.39, 0.03, 0.62, 0.17),
    "chest": (0.27, 0.175, 0.73, 0.38),
    "stomach": (0.30, 0.38, 0.71, 0.565),
    "left arm": (0.05, 0.175, 0.30, 0.58),
    "right arm": (0.73, 0.175, 0.96, 0.58),
    "left leg": (0.30, 0.565, 0.52, 0.98),
    "right leg": (0.52, 0.565, 0.71, 0.98),
}


def _picture():
    import sys
    from pathlib import Path
    from PySide6.QtGui import QPixmap
    here = Path(__file__).resolve().parent.parent
    for base in (here, here / "_internal"):
        f = base / "assets" / "modes" / "body_xray.png"
        if f.exists():
            pm = QPixmap(str(f))
            if not pm.isNull():
                return pm
    return None


class BodyHud(QWidget):
    zone_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(340)
        self.setMouseTracking(True)
        self._t = 0.0
        self._hover: str | None = None
        self._picked: str | None = None
        self._pm = _picture()
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
    def _rect(self) -> QRectF:
        """Where the picture sits inside the widget (kept in proportion, with room for the label and the trace)."""
        if self._pm is None:
            return QRectF(0, 0, 0, 0)
        avail = QRectF(0, 14, self.width(), self.height() - 14 - 26)
        k = min(avail.width() / self._pm.width(), avail.height() / self._pm.height())
        w, h = self._pm.width() * k, self._pm.height() * k
        return QRectF(avail.center().x() - w / 2, avail.top(), w, h)

    def _zone_at(self, pos) -> str | None:
        r = self._rect()
        if r.width() <= 0 or not r.contains(pos):
            return None
        fx, fy = (pos.x() - r.left()) / r.width(), (pos.y() - r.top()) / r.height()
        for name, (l, t, rr, b) in ZONES.items():
            if l <= fx <= rr and t <= fy <= b:
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

    def _draw_heart(self, p: QPainter, r: QRectF) -> None:
        """A small red heart in the chest, beating (a quick double pulse, then a rest)."""
        ph = (self._t / 1.1) % 1.0
        beat = max(math.exp(-((ph - 0.08) / 0.05) ** 2), 0.7 * math.exp(-((ph - 0.26) / 0.06) ** 2))
        c = QPointF(r.left() + 0.545 * r.width(), r.top() + 0.285 * r.height())
        s = r.width() * 0.062 * (1.0 + 0.16 * beat)
        glow = QRadialGradient(c, s * 2.6)
        glow.setColorAt(0.0, QColor(255, 60, 70, int(120 + 100 * beat)))
        glow.setColorAt(1.0, QColor(255, 60, 70, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(c, s * 2.6, s * 2.6)
        heart = QPainterPath()
        heart.moveTo(c.x(), c.y() + s * 0.95)
        heart.cubicTo(c.x() - s * 1.6, c.y() - s * 0.1, c.x() - s * 0.9, c.y() - s * 1.2, c.x(), c.y() - s * 0.35)
        heart.cubicTo(c.x() + s * 0.9, c.y() - s * 1.2, c.x() + s * 1.6, c.y() - s * 0.1, c.x(), c.y() + s * 0.95)
        g = QRadialGradient(QPointF(c.x() - s * 0.3, c.y() - s * 0.3), s * 1.8)
        g.setColorAt(0.0, QColor(255, 140, 150))
        g.setColorAt(1.0, QColor(225, 30, 55))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor(255, 190, 195, 200), 1))
        p.drawPath(heart)

    # -- drawing: your X-ray picture, alive: a scan band sweeps down it and the part you touch lights up -------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        r = self._rect()
        pulse = 0.5 + 0.5 * math.sin(self._t * 2.2)
        if self._pm is not None:
            p.setOpacity(0.88 + 0.12 * pulse)
            p.drawPixmap(r, self._pm, QRectF(self._pm.rect()))
            p.setOpacity(1.0)
            for name, (l, t, rr, b) in ZONES.items():
                if name == self._hover or name == self._picked:
                    zr = QRectF(r.left() + l * r.width(), r.top() + t * r.height(), (rr - l) * r.width(), (b - t) * r.height())
                    p.setPen(QPen(QColor(150, 215, 255, 230), 1.4, Qt.DashLine))
                    p.setBrush(QBrush(QColor(120, 190, 255, 60 if name == self._hover else 40)))
                    p.drawRoundedRect(zr, 8, 8)
            self._draw_heart(p, r)
            y = r.top() + ((self._t * 0.18) % 1.0) * r.height()         # the scan band
            band = QLinearGradient(0, y - 14, 0, y + 14)
            band.setColorAt(0.0, QColor(120, 200, 255, 0))
            band.setColorAt(0.5, QColor(150, 215, 255, 110))
            band.setColorAt(1.0, QColor(120, 200, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(band))
            p.drawRect(QRectF(r.left(), y - 14, r.width(), 28))
        # heartbeat trace along the bottom
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
