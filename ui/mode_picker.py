"""The mode picker: a ring of ten glowing segments like an arc reactor. Each lit segment is one mode of EV AI;
the dark ones are free slots for modes that are coming later. Click a lit segment to switch to that mode."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QDialog

SLOTS = 10


class ModePicker(QDialog):
    chosen = Signal(str)

    def __init__(self, parent, modes: list[tuple[str, str]], current: str):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setMouseTracking(True)
        self.resize(580, 580)
        self._modes = modes[:SLOTS]
        self._current = current
        self._hover = -1

    # -- geometry -------------------------------------------------------------------------------
    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _slot_at(self, pos) -> int:
        c = self._center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        dist = math.hypot(dx, dy)
        if dist < 105 or dist > 210:
            return -1
        ang = math.degrees(math.atan2(dx, -dy)) % 360      # clockwise from the top
        return int(((ang + 360 / SLOTS / 2) % 360) // (360 / SLOTS))

    # -- input ----------------------------------------------------------------------------------
    def mouseMoveEvent(self, e) -> None:
        i = self._slot_at(e.position())
        if i != self._hover:
            self._hover = i
            self.setCursor(Qt.PointingHandCursor if 0 <= i < len(self._modes) else Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, e) -> None:
        i = self._slot_at(e.position())
        if 0 <= i < len(self._modes):
            self.chosen.emit(self._modes[i][0])
            self.accept()
        elif math.hypot(e.position().x() - self._center().x(), e.position().y() - self._center().y()) > 262:
            self.reject()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(e)

    # -- drawing --------------------------------------------------------------------------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self._center()
        p.setPen(QPen(QColor(120, 200, 255, 90), 1.5))
        p.setBrush(QColor(6, 10, 18, 238))
        p.drawEllipse(c, 262, 262)
        # silver ring
        ring = QPen(QColor(168, 176, 188), 16)
        p.setPen(ring)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, 214, 214)
        p.setPen(QPen(QColor(235, 240, 248, 150), 2))
        p.drawEllipse(c, 222, 222)
        p.setPen(QPen(QColor(60, 66, 78), 2))
        p.drawEllipse(c, 205, 205)
        # the ten coils
        for i in range(SLOTS):
            self._coil(p, c, i)
        # labels outside the coils
        f = QFont("Segoe UI", 9)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(f)
        for i, (_k, label) in enumerate(self._modes):
            ang = math.radians(i * 360 / SLOTS)
            r = 238
            x, y = c.x() + r * math.sin(ang), c.y() - r * math.cos(ang)
            p.setPen(QColor(150, 225, 255) if i == self._hover or self._modes[i][0] == self._current else QColor(120, 150, 175))
            p.drawText(QRectF(x - 50, y - 10, 100, 20), Qt.AlignCenter, label)
        # the glowing core in the middle
        g = QRadialGradient(c, 92)
        g.setColorAt(0.0, QColor(255, 255, 255))
        g.setColorAt(0.35, QColor(170, 235, 255))
        g.setColorAt(0.75, QColor(40, 140, 230, 200))
        g.setColorAt(1.0, QColor(10, 40, 90, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, 92, 92)
        p.setPen(QPen(QColor(20, 60, 110, 190), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, 52, 52)
        p.drawEllipse(c, 38, 38)
        name = "SELECT MODE"
        if 0 <= self._hover < len(self._modes):
            name = self._modes[self._hover][1]
        else:
            for k, label in self._modes:
                if k == self._current:
                    name = label
        f2 = QFont("Segoe UI", 10)
        f2.setBold(True)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(f2)
        p.setPen(QColor(8, 30, 60))
        p.drawText(QRectF(c.x() - 60, c.y() - 12, 120, 24), Qt.AlignCenter, name)
        p.end()

    def _coil(self, p: QPainter, c: QPointF, i: int) -> None:
        used = i < len(self._modes)
        active = used and self._modes[i][0] == self._current
        hot = used and i == self._hover
        p.save()
        p.translate(c)
        p.rotate(i * 360 / SLOTS)
        rect = QRectF(-24, -190, 48, 62)
        if used:
            base = QColor(90, 210, 255) if (active or hot) else QColor(30, 120, 215)
            edge = QColor(190, 240, 255) if (active or hot) else QColor(90, 170, 235)
        else:
            base, edge = QColor(24, 30, 42), QColor(52, 62, 80)
        if used and (active or hot):                                  # glow
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(80, 200, 255, 60))
            p.drawRoundedRect(rect.adjusted(-7, -7, 7, 7), 14, 14)
        p.setPen(QPen(edge, 2))
        p.setBrush(base)
        p.drawRoundedRect(rect, 9, 9)
        # copper windings across the coil
        p.setPen(QPen(QColor(184, 115, 51) if used else QColor(70, 56, 46), 2))
        y = rect.top() + 8
        while y < rect.bottom() - 4:
            p.drawLine(QPointF(rect.left() + 5, y), QPointF(rect.right() - 5, y))
            y += 6
        p.restore()
