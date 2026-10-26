"""Video mode camera window: the live webcam feed with a sci-fi HUD on top —
two rotating rings at the bottom corners, and a targeting reticle locked onto
your eye that follows you around. Small by default; the — button shrinks it to
a little EV badge (click the badge to bring it back), drag the corner to resize.
Closing it turns Video mode off."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from ui import theme as _theme

_LOGO = Path(__file__).resolve().parent.parent / "assets" / "icons" / "ev_logo.png"
_PILL = 84          # size of the shrunk badge
_cyan = (125, 212, 232)


def _c(alpha: int) -> QColor:
    return QColor(_cyan[0], _cyan[1], _cyan[2], alpha)


class VideoViewWindow(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(240, 180)
        self.resize(380, 285)
        self._collapsed = False
        self._full_size = (380, 285)
        self._press_pos = None
        self._moved = False
        self._logo = QPixmap(str(_LOGO))

        self._pixmap: QPixmap | None = None
        self._frame_size = (4, 3)
        self._hand = None            # (x, y) normalised, from the tracker
        self._eye = None             # (x, y) normalised eye position from the face tracker
        self._reticle = QPointF(0.55, 0.32)   # smoothed, normalised
        self._angle = 0.0
        self._s = 1.0
        self._digits = "0927092703897098"
        self._status = "Starting camera..."
        self._state = "on"           # "on" | "paused" | "off" | "error" (gesture control)
        self._gesture = ""
        self._drag = None
        self._resizing = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._digit_timer = QTimer(self)
        self._digit_timer.timeout.connect(self._shuffle_digits)

    # -- public API -----------------------------------------------------
    def set_frame(self, data: dict) -> None:
        qimage = (data or {}).get("clean") or (data or {}).get("qimage")
        if qimage is None:
            return
        self._pixmap = QPixmap.fromImage(qimage)
        self._frame_size = (max(1, qimage.width()), max(1, qimage.height()))
        self._hand = (data or {}).get("hand")
        self._eye = (data or {}).get("eye")
        self._state = (data or {}).get("state", self._state)
        self._gesture = (data or {}).get("gesture", "")

    def set_status(self, text: str) -> None:
        self._status = text

    def show_centered(self) -> None:
        """(Name kept for callers) Shows the small window in the bottom-left corner."""
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            w = min(self.width(), int(geo.width() * 0.5))
            h = min(self.height(), int(geo.height() * 0.5))
            self.resize(w, h)
            self.move(geo.left() + 24, geo.bottom() - h - 24)
        self.show()
        self.raise_()

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        if collapsed:
            self._full_size = (self.width(), self.height())
            self.setMinimumSize(_PILL, _PILL)
            self.resize(_PILL, _PILL)
        else:
            self.setMinimumSize(240, 180)
            self.resize(*self._full_size)
        self.update()

    def showEvent(self, event) -> None:
        self._timer.start(33)
        self._digit_timer.start(140)
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        self._digit_timer.stop()
        super().hideEvent(event)

    # -- animation --------------------------------------------------------
    def _tick(self) -> None:
        self._angle = (self._angle + 1.6) % 360
        if self._eye is not None:
            # map the eye from camera-frame space to window space (the feed is cropped to fill)
            fw, fh = self._frame_size
            w, h = max(1, self.width()), max(1, self.height())
            scale = max(w / fw, h / fh)
            ox, oy = (w - fw * scale) / 2, (h - fh * scale) / 2
            tx = (ox + self._eye[0] * fw * scale) / w
            ty = (oy + self._eye[1] * fh * scale) / h
        else:
            # idle: drift gently so it looks alive
            tx = 0.55 + 0.03 * math.sin(math.radians(self._angle))
            ty = 0.32 + 0.02 * math.cos(math.radians(self._angle * 1.3))
        k = 0.35
        self._reticle = QPointF(
            self._reticle.x() + (tx - self._reticle.x()) * k,
            self._reticle.y() + (ty - self._reticle.y()) * k,
        )
        self.update()

    def _shuffle_digits(self) -> None:
        self._digits = "".join(random.choice("0123456789") for _ in range(16))

    # -- input ------------------------------------------------------------
    def _close_rect(self) -> QRectF:
        return QRectF(self.width() - 34, 8, 24, 24)

    def _shrink_rect(self) -> QRectF:
        return QRectF(self.width() - 64, 8, 24, 24)

    def _grip_rect(self) -> QRectF:
        return QRectF(self.width() - 26, self.height() - 26, 26, 26)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = event.position()
        self._moved = False
        if not self._collapsed:
            if self._close_rect().contains(pos):
                self.close()
                return
            if self._shrink_rect().contains(pos):
                self.set_collapsed(True)
                return
            if self._grip_rect().contains(pos):
                self._resizing = (event.globalPosition().toPoint(), self.size())
                return
        self._resizing = None
        self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        self._press_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.LeftButton):
            return
        resizing = getattr(self, "_resizing", None)
        if resizing is not None:
            delta = event.globalPosition().toPoint() - resizing[0]
            self.resize(max(240, resizing[1].width() + delta.x()), max(180, resizing[1].height() + delta.y()))
            return
        if self._drag is not None:
            if self._press_pos is not None and (event.globalPosition().toPoint() - self._press_pos).manhattanLength() > 4:
                self._moved = True
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:
        # A click (not a drag) on the shrunk badge brings the window back.
        if self._collapsed and not self._moved:
            self.set_collapsed(False)
        self._drag = None
        self._resizing = None
        self._press_pos = None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self._digit_timer.stop()
        self.closed.emit()
        super().closeEvent(event)

    # -- painting ---------------------------------------------------------
    def paintEvent(self, event) -> None:
        global _cyan
        hl = _theme.highlight()
        _cyan = (hl.red(), hl.green(), hl.blue())
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            w, h = self.width(), self.height()
            if self._collapsed:
                self._paint_pill(painter, w, h)
                return
            self._s = max(0.42, min(1.2, min(w, h) / 560.0))
            rect = QRectF(1, 1, w - 2, h - 2)

            clip = QPainterPath()
            clip.addRoundedRect(rect, 10, 10)
            painter.setClipPath(clip)
            painter.fillRect(self.rect(), QColor(4, 8, 14))

            if self._pixmap is not None and not self._pixmap.isNull():
                scaled = self._pixmap.scaled(
                    self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                painter.drawPixmap((w - scaled.width()) // 2, (h - scaled.height()) // 2, scaled)
            else:
                painter.setPen(_c(160))
                painter.drawText(self.rect(), Qt.AlignCenter, "STARTING CAMERA...")

            self._draw_reticle(painter, QPointF(self._reticle.x() * w, self._reticle.y() * h), w)

            painter.setClipping(False)

            # status line
            painter.setPen(_c(190))
            f = QFont("Consolas")
            f.setPointSizeF(max(6.0, 9 * self._s))
            f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
            painter.setFont(f)
            painter.drawText(QRectF(0, h - 26, w, 18), Qt.AlignCenter, self._status.upper()[:60])

            # camera / gesture state badge (top-left)
            colour, text = {
                "on": (QColor(70, 220, 120), "CAMERA ON · GESTURES ON"),
                "paused": (QColor(255, 190, 60), "PAUSED · FIST TO RESUME"),
                "off": (QColor(150, 160, 175), "CAMERA ON · GESTURES OFF"),
                "error": (QColor(255, 80, 80), "CAMERA ERROR"),
            }.get(self._state, (QColor(70, 220, 120), "CAMERA ON"))
            badge_font = QFont("Consolas")
            badge_font.setPointSizeF(max(6.0, 8 * self._s))
            painter.setFont(badge_font)
            painter.setPen(Qt.NoPen)
            painter.setBrush(colour)
            painter.drawEllipse(QPointF(16, 16), 4, 4)
            painter.setPen(colour)
            top = text + (f"  ·  {self._gesture.upper()}" if self._gesture and self._state == "on" else "")
            painter.drawText(QRectF(26, 6, w - 90, 20), Qt.AlignLeft | Qt.AlignVCenter, top)

            # shrink + close buttons
            painter.setPen(QPen(_c(200), 2))
            painter.setBrush(QColor(0, 0, 0, 110))
            sr = self._shrink_rect()
            painter.drawEllipse(sr)
            painter.drawLine(QPointF(sr.left() + 7, sr.center().y()), QPointF(sr.right() - 7, sr.center().y()))
            cr = self._close_rect()
            painter.drawEllipse(cr)
            m = 8
            painter.drawLine(QPointF(cr.left() + m, cr.top() + m), QPointF(cr.right() - m, cr.bottom() - m))
            painter.drawLine(QPointF(cr.right() - m, cr.top() + m), QPointF(cr.left() + m, cr.bottom() - m))

            # resize grip
            gr = self._grip_rect()
            painter.setPen(QPen(_c(170), 2))
            for i in (6, 12, 18):
                painter.drawLine(QPointF(gr.right() - 4, gr.bottom() - i), QPointF(gr.right() - i, gr.bottom() - 4))

            # frame border
            painter.setPen(QPen(QColor(205, 205, 220, 190), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 10, 10)
        finally:
            painter.end()

    def _paint_pill(self, painter: QPainter, w: int, h: int) -> None:
        """The shrunk state: a small round EV badge with a glowing ring. Click to expand."""
        c = QPointF(w / 2, h / 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(6, 10, 18, 235))
        painter.drawEllipse(c, w / 2 - 2, h / 2 - 2)
        if not self._logo.isNull():
            d = w - 14
            painter.save()
            painter.translate(c)
            painter.rotate(self._angle * 0.5)
            painter.drawPixmap(QRectF(-d / 2, -d / 2, d, d), self._logo, QRectF(self._logo.rect()))
            painter.restore()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_c(220), 2))
        painter.drawEllipse(c, w / 2 - 2, h / 2 - 2)

    # -- HUD pieces -------------------------------------------------------
    @staticmethod
    def _arc(painter: QPainter, c: QPointF, r: float, start_deg: float, span_deg: float) -> None:
        painter.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), int(-start_deg * 16), int(-span_deg * 16))

    def _ticks(self, painter: QPainter, c: QPointF, r: float, count: int, length: float, offset: float) -> None:
        for i in range(count):
            a = math.radians(offset + i * 360.0 / count)
            painter.drawLine(
                QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r),
                QPointF(c.x() + math.cos(a) * (r - length), c.y() + math.sin(a) * (r - length)),
            )

    def _draw_left_ring(self, painter: QPainter, c: QPointF, r: float) -> None:
        a = self._angle
        painter.setBrush(Qt.NoBrush)
        # big outer arcs
        painter.setPen(QPen(_c(110), max(3, r * 0.05), Qt.SolidLine, Qt.FlatCap))
        for start, span in ((20, 110), (170, 40), (250, 70)):
            self._arc(painter, c, r * 1.28, start + a * 0.5, span)
        # middle ring, counter-rotating
        painter.setPen(QPen(_c(170), max(2, r * 0.035), Qt.SolidLine, Qt.FlatCap))
        for start, span in ((0, 80), (100, 60), (190, 90), (300, 40)):
            self._arc(painter, c, r * 0.95, start - a * 0.8, span)
        # ticks
        painter.setPen(QPen(_c(150), 2))
        self._ticks(painter, c, r * 0.80, 24, r * 0.07, a)
        # inner thin ring
        painter.setPen(QPen(_c(120), 1.5))
        painter.drawEllipse(c, r * 0.62, r * 0.62)
        # four arrowheads pointing at the centre
        painter.setPen(Qt.NoPen)
        painter.setBrush(_c(190))
        for k in range(4):
            ang = math.radians(45 + 90 * k)
            tip = QPointF(c.x() + math.cos(ang) * r * 0.16, c.y() + math.sin(ang) * r * 0.16)
            base = r * 0.30
            left = QPointF(c.x() + math.cos(ang + 0.45) * base, c.y() + math.sin(ang + 0.45) * base)
            right = QPointF(c.x() + math.cos(ang - 0.45) * base, c.y() + math.sin(ang - 0.45) * base)
            path = QPainterPath(tip)
            path.lineTo(left)
            path.lineTo(right)
            path.closeSubpath()
            painter.drawPath(path)

    def _draw_right_ring(self, painter: QPainter, c: QPointF, r: float) -> None:
        a = self._angle
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_c(150), max(3, r * 0.04), Qt.SolidLine, Qt.FlatCap))
        for start, span in ((200, 150), (10, 70)):
            self._arc(painter, c, r * 1.22, start + a * 0.6, span)
        painter.setPen(QPen(_c(190), max(2, r * 0.03), Qt.SolidLine, Qt.FlatCap))
        for start, span in ((0, 120), (140, 100), (270, 60)):
            self._arc(painter, c, r * 0.95, start - a * 0.5, span)
        painter.setPen(QPen(_c(140), 2))
        self._ticks(painter, c, r * 0.80, 18, r * 0.08, -a)
        # orbiting marker
        ang = math.radians(a * 1.4)
        mp = QPointF(c.x() + math.cos(ang) * r * 0.95, c.y() + math.sin(ang) * r * 0.95)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_c(230))
        tri = QPainterPath(QPointF(mp.x() + 10, mp.y()))
        tri.lineTo(mp.x() - 6, mp.y() - 7)
        tri.lineTo(mp.x() - 6, mp.y() + 7)
        tri.closeSubpath()
        painter.drawPath(tri)

    def _draw_reticle(self, painter: QPainter, p: QPointF, w: int) -> None:
        a = self._angle
        k = self._s
        # glowing core
        g = QRadialGradient(p, 34 * k)
        g.setColorAt(0.0, QColor(90, 190, 245, 235))
        g.setColorAt(0.8, QColor(35, 105, 170, 220))
        g.setColorAt(1.0, QColor(20, 70, 120, 200))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(g))
        painter.drawEllipse(p, 34 * k, 34 * k)

        # X in the centre
        painter.setPen(QPen(QColor(150, 225, 255, 240), max(2.0, 3 * k), Qt.SolidLine, Qt.RoundCap))
        for dx, dy in ((-9 * k, -9 * k), (9 * k, 9 * k)):
            painter.drawLine(QPointF(p.x() + dx, p.y() + dy), QPointF(p.x() - dx, p.y() - dy))

        # rotating outer arcs
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_c(215), max(2.5, 4 * k), Qt.SolidLine, Qt.FlatCap))
        for start, span in ((30, 110), (200, 60)):
            self._arc(painter, p, 46 * k, start + a * 1.2, span)
        painter.setPen(QPen(_c(150), 2))
        self._arc(painter, p, 54 * k, -a * 0.9, 220)
