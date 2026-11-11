"""The mode picker: a ring of twelve glowing segments like an arc reactor. Each lit segment is one mode of EV AI;
the dark ones are free slots for modes that are coming later. Click a lit segment to switch to that mode."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontInfo, QFontMetricsF, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QDialog

SLOTS = 12


class ModePicker(QDialog):
    chosen = Signal(str)

    def __init__(self, parent, modes: list[tuple[str, str]], active: set[str]):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setMouseTracking(True)
        self.resize(500, 500)
        self._modes = modes[:SLOTS]
        self._active = set(active)
        self._hover = -1
        self._core_hover = False

    # -- geometry -------------------------------------------------------------------------------
    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _in_core(self, pos) -> bool:
        c = self._center()
        return math.hypot(pos.x() - c.x(), pos.y() - c.y()) < 70

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
        core = self._in_core(e.position())
        if i != self._hover or core != self._core_hover:
            self._hover, self._core_hover = i, core
            self.setCursor(Qt.PointingHandCursor if (0 <= i < len(self._modes) or core) else Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, e) -> None:
        i = self._slot_at(e.position())
        if self._in_core(e.position()):                     # the glowing centre: Overdrive (90 seconds)
            self.chosen.emit("overdrive")
            self.accept()
        elif 0 <= i < len(self._modes):
            self.chosen.emit(self._modes[i][0])
            self.accept()
        elif math.hypot(e.position().x() - self._center().x(), e.position().y() - self._center().y()) > 244:
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
        p.drawEllipse(c, 244, 244)
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
        if self._core_hover or "overdrive" in self._active:
            name = "OVERDRIVE"
        elif 0 <= self._hover < len(self._modes):
            name = self._modes[self._hover][1]
        else:
            on = [label for k, label in self._modes if k in self._active]
            if len(on) == 1:
                name = on[0]
            elif on:
                name = f"{len(on)} ON"
        f2 = QFont("Segoe UI", 10)
        f2.setBold(True)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(f2)
        p.setPen(QColor(8, 30, 60))
        p.drawText(QRectF(c.x() - 60, c.y() - 12, 120, 24), Qt.AlignCenter, name)
        if name == "OVERDRIVE":
            f3 = QFont("Segoe UI", 7)
            p.setFont(f3)
            p.drawText(QRectF(c.x() - 60, c.y() + 8, 120, 16), Qt.AlignCenter, "90 SECONDS")
        p.end()

    _TRACES = (   # the circuit pattern on a card, as polylines in a 0..1 box (like the FRIDAY card)
        ((0.18, 1.0), (0.18, 0.62), (0.34, 0.46), (0.34, 0.0)),
        ((0.5, 1.0), (0.5, 0.0)),
        ((0.82, 1.0), (0.82, 0.58), (0.66, 0.42), (0.66, 0.0)),
        ((0.34, 0.8), (0.5, 0.8)),
        ((0.5, 0.3), (0.66, 0.3)),
    )

    def _coil(self, p: QPainter, c: QPointF, i: int) -> None:
        """One mode as a small card, like the FRIDAY card: a blue circuit board with the name on a white label on top."""
        used = i < len(self._modes)
        label = self._modes[i][1] if used else ""
        active = used and self._modes[i][0] in self._active
        hot = used and i == self._hover
        lit = active or hot
        ang = math.radians(i * 360 / SLOTS)
        cx, cy = c.x() + 158 * math.sin(ang), c.y() - 158 * math.cos(ang)
        w, h = 52.0, 66.0
        card = QRectF(cx - w / 2, cy - h / 2, w, h)
        if lit:                                                       # glow behind a lit card
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(90, 210, 255, 70))
            p.drawRoundedRect(card.adjusted(-7, -7, 7, 7), 11, 11)
        # black case
        p.setPen(QPen(QColor(150, 170, 190) if lit else QColor(70, 82, 98), 1.5))
        p.setBrush(QColor(10, 14, 22))
        p.drawRoundedRect(card, 6, 6)
        # label strip on top
        strip = QRectF(card.left() + 3, card.top() + 3, w - 6, 15)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(246, 248, 250) if used else QColor(40, 48, 62))
        p.drawRoundedRect(strip, 2.5, 2.5)
        # blue circuit panel
        panel = QRectF(card.left() + 3, strip.bottom() + 3, w - 6, card.bottom() - strip.bottom() - 6)
        g = QLinearGradient(panel.topLeft(), panel.bottomLeft())
        if used:
            g.setColorAt(0.0, QColor(120, 215, 255) if lit else QColor(40, 150, 235))
            g.setColorAt(1.0, QColor(20, 90, 200) if lit else QColor(10, 60, 150))
        else:
            g.setColorAt(0.0, QColor(30, 38, 52))
            g.setColorAt(1.0, QColor(18, 24, 34))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(panel, 3, 3)
        trace = QPen(QColor(235, 248, 255, 230) if used else QColor(70, 80, 96), 1.4)
        p.setPen(trace)
        for line in self._TRACES:
            pts = [QPointF(panel.left() + 3 + (panel.width() - 6) * x, panel.top() + 2 + (panel.height() - 4) * y) for x, y in line]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
        p.setBrush(QColor(235, 248, 255) if used else QColor(70, 80, 96))
        for x, y in ((0.34, 0.0), (0.66, 0.0), (0.5, 0.0), (0.18, 1.0), (0.5, 1.0), (0.82, 1.0)):
            p.drawEllipse(QPointF(panel.left() + 3 + (panel.width() - 6) * x, panel.top() + 2 + (panel.height() - 4) * y), 1.6, 1.6)
        # the name, written on the label
        if used:
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
            p.setPen(QColor(10, 20, 40))
            p.drawText(strip, Qt.AlignCenter, label)
