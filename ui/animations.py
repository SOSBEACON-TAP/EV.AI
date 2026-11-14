"""
ui/animations.py
-----------------
The animated "AI core" — EV AI's original visual identity element.
It is a custom-painted QWidget (not an image) so it can smoothly change
color and speed based on the current AIState, with no external assets.

Design notes (kept deliberately different from any franchise UI):
- Two tilted elliptical rings (one red, one blue) spin around the center
  in opposite directions, crossing each other like orbiting bands.
- A faint rotating "web" of radial lines + concentric circles sits behind
  them, and two diagonal beams sweep across the whole thing.
- A bright pulsing core sits at the center where everything crosses.
- Color/speed comes entirely from AIState.accent_hex / _speed_for_state,
  so adding a new state only requires adding a color in core/state.py.
"""

import math
from PySide6.QtCore import Qt, QTimer, Signal, QPointF, QRectF
from pathlib import Path
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap, QRadialGradient, QBrush
from PySide6.QtWidgets import QWidget

from core.state import AIState
from ui import theme as _theme


# Mouths: (left, top, right, bottom) as fractions of the picture, and how far the mouth opens.
_MOUTHS = {
    "tars": (0.28, 0.72, 0.70, 0.80, 3.0),       # the blue bar becomes a thick bar
    "gideon": (0.42, 0.50, 0.58, 0.57, 1.4),
    "friday": (0.36, 0.62, 0.64, 0.74, 1.0),
    "ultron": (0.30, 0.66, 0.70, 0.80, 0.5),
}
# Baymax has no mouth: the line between his eyes thickens as he speaks. (x0, y0, x1, y1) of the line.
_MOUTH_LINE = {"baymax": (0.345, 0.504, 0.685, 0.587)}
# Blinking: the eyes squash shut for a moment. shape, cover colour, line colour, then the eye boxes (l, t, r, b).
_EYES = {
    "baymax": ("ellipse", (244, 245, 247), (10, 10, 12), [(0.225, 0.37, 0.36, 0.60), (0.655, 0.45, 0.80, 0.68)]),
    "tars": ("rect", (4, 10, 20), (70, 190, 255), [(0.14, 0.36, 0.34, 0.52), (0.59, 0.36, 0.80, 0.52)]),
}
_FLICKER = {"gideon", "jarvis", "game", "friday", "karen"}      # holograms: a faint electrical shimmer


def _face_path(key: str):
    here = Path(__file__).resolve().parent.parent
    for base in (here, here / "_internal"):
        f = base / "assets" / "modes" / f"{key}.png"
        if f.exists():
            return f
    return None


class AICoreWidget(QWidget):
    """Custom-painted animated indicator representing EV's current state."""

    state_changed = Signal(AIState)
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 160)
        self._state = AIState.IDLE
        self._angle = 0.0          # base rotation angle, degrees
        self._pulse_phase = 0.0    # 0..1 pulse cycle position
        self._jarvis = False       # all-yellow look when Jarvis is switched on
        self._ultron = False       # all-red look when Ultron is switched on
        self._tint = None          # (ring1, ring2) hex colours for Game / Karen mode
        self._face = None          # the picture of the current mode (Tars, Gideon, glasses...)
        self._face_key = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)  # ~33 FPS, light on CPU

    # -- public API -----------------------------------------------------
    def set_state(self, state: AIState) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)
            self.update()

    def state(self) -> AIState:
        return self._state

    def palette_colors(self):
        """(centre accent, ring colour 1, ring colour 2) — all gold in Jarvis mode."""
        accent = QColor(self._state.accent_hex)
        red, blue = _theme.core_colors()
        if self._jarvis:
            red, blue = QColor("#FFC400"), QColor("#FFE066")
            if self._state != AIState.ERROR:
                accent = QColor("#FFC400")
        if self._ultron:
            red, blue = QColor("#FF2A2A"), QColor("#C81010")
            if self._state != AIState.ERROR:
                accent = QColor("#FF2A2A")
        if self._tint:
            red, blue = QColor(self._tint[0]), QColor(self._tint[1])
            if self._state != AIState.ERROR:
                accent = QColor(self._tint[0])
        return accent, red, blue

    def set_face(self, key) -> None:
        """Show the face picture of a mode in the middle of the core (None = the plain EV core)."""
        if key == self._face_key:
            return
        self._face_key = key
        self._face = None
        if key:
            f = _face_path(key)
            if f is not None:
                pm = QPixmap(str(f))
                self._face = pm if not pm.isNull() else None
        self.setCursor(Qt.PointingHandCursor if key == "edith" else Qt.ArrowCursor)
        self.update()

    def face_key(self):
        return self._face_key

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _face_clock(self):
        """Smooth animation state (seconds, mouth openness 0..1, blink 0..1), advanced once per frame."""
        import time as _t
        now = _t.monotonic()
        dt = min(0.1, max(0.001, now - getattr(self, "_fc_last", now)))
        self._fc_last = now
        speaking = self._state == AIState.SPEAKING
        # speech rhythm: a new "syllable" about 8 times a second, with a short pause every few words
        k = int(now * 8)
        h = (k * 2654435761) & 0xFFFFFFFF
        target = 0.25 + 0.75 * ((h >> 8) % 100) / 100.0
        if (k // 9) % 3 == 2 and (k % 9) > 5:
            target = 0.0
        if not speaking:
            target = 0.0
        v = getattr(self, "_mouth_v", 0.0)
        v += (target - v) * (1 - math.exp(-dt * (34 if target > v else 16)))      # opens fast, closes a little slower
        self._mouth_v = v
        # blinking every 2.5 to 6 seconds
        nb = getattr(self, "_next_blink", now + 3.0)
        blink = 0.0
        if now >= nb:
            span = now - nb
            blink = 1 - abs(span / 0.09 - 1) if span < 0.18 else 0.0
            if span >= 0.18:
                self._next_blink = now + 2.5 + (((int(now * 1000) * 40503) & 0xFFFF) / 65535.0) * 3.5
        else:
            self._next_blink = nb
        return now, v, max(0.0, blink)

    def _draw_face(self, painter, cx, cy, radius, accent) -> None:
        """The mode's picture on its own, alive: it floats, sways and breathes, glows in the mode colour and has a scan
        line sliding over it. Eyes blink; a speaking mouth moves with a speech rhythm and the head nods a little.
        Listening sends out ripples, thinking sends sparks around it, speaking makes it pulse."""
        pm = self._face
        now, mouth_v, blink = self._face_clock()
        ph = self._pulse_phase * 2 * math.pi
        st = self._state
        key = self._face_key
        box = radius * 1.7
        scale = min(box / pm.width(), box / pm.height())
        if pm.width() > pm.height() * 1.8:                      # wide pictures (glasses, Jarvis) use the full width
            scale = (radius * 2.0) / pm.width()
        speaking = st == AIState.SPEAKING
        breathe = 1.0 + 0.02 * math.sin(ph) + (0.025 * mouth_v if speaking else 0.0)
        tw, th = pm.width() * scale * breathe, pm.height() * scale * breathe
        cy = cy + math.sin(ph) * radius * 0.03                   # a slow float
        cx = cx + math.sin(now * 0.7) * radius * 0.012
        big = max(tw, th)

        col = QColor("#FF5252") if st == AIState.ERROR else QColor(accent)
        beat = 0.5 + 0.5 * math.sin(ph * (3 if speaking else 1))
        room = min(self.width(), self.height()) / 2 - 2           # a glow must fade out before the edge of this widget
        for rad, a0 in ((0.85, 34), (0.6, 70)):                  # two soft layers of glow
            gr = min(big * rad, room)
            glow = QRadialGradient(cx, cy, gr)
            col.setAlpha(int(a0 * (0.6 + 0.7 * beat)))
            glow.setColorAt(0.0, col)
            col.setAlpha(int(a0 * (0.6 + 0.7 * beat) * 0.35))
            glow.setColorAt(0.55, col)
            col.setAlpha(0)
            glow.setColorAt(1.0, col)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(cx, cy), gr, gr)

        if st == AIState.LISTENING:                              # ripples spreading outwards
            for k in range(3):
                t = (self._pulse_phase * 2 + k / 3) % 1.0
                c = QColor(accent)
                c.setAlpha(int(150 * (1 - t) ** 1.5))
                painter.setPen(QPen(c, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), big * (0.45 + 0.5 * t), big * (0.45 + 0.5 * t))
        elif st in (AIState.THINKING, AIState.PROCESSING, AIState.EXECUTING):   # sparks circling, with fading trails
            painter.setPen(Qt.NoPen)
            for k in range(6):
                for tr in range(5):
                    a = math.radians(self._angle * 3 + k * 60 - tr * 7)
                    c = QColor(accent)
                    c.setAlpha(int((230 if k == 0 else 150) * (1 - tr / 5)))
                    painter.setBrush(c)
                    rr = 4 - tr * 0.55
                    painter.drawEllipse(QPointF(cx + math.cos(a) * big * 0.62, cy + math.sin(a) * big * 0.62), rr, rr)

        w, h = int(tw), int(th)
        if w < 8 or h < 8:
            return
        layer = QPixmap(w, h)
        layer.fill(Qt.transparent)
        lp = QPainter(layer)
        lp.setRenderHint(QPainter.Antialiasing)
        lp.setRenderHint(QPainter.SmoothPixmapTransform)
        lp.drawPixmap(0, 0, w, h, pm)

        mouth = _MOUTHS.get(key)
        if mouth and mouth_v > 0.02:                             # the mouth opens and closes with the speech
            x0, y0, x1, y1, gain = mouth
            sx0, sy0, sx1, sy1 = int(x0 * pm.width()), int(y0 * pm.height()), int(x1 * pm.width()), int(y1 * pm.height())
            dw, dh = (x1 - x0) * w, (y1 - y0) * h
            grow = 1.0 + gain * mouth_v
            cxm, cym = (x0 + x1) / 2 * w, (y0 + y1) / 2 * h
            lp.drawPixmap(QRectF(cxm - dw / 2, cym - dh * grow / 2, dw, dh * grow), pm,
                          QRectF(sx0, sy0, sx1 - sx0, sy1 - sy0))
        line = _MOUTH_LINE.get(key)
        if line:                                                 # Baymax: the line between his eyes thickens as he talks
            lp.setPen(QPen(QColor(10, 10, 12), max(1.0, w * (0.006 + 0.03 * mouth_v)), Qt.SolidLine, Qt.RoundCap))
            lp.drawLine(QPointF(line[0] * w, line[1] * h), QPointF(line[2] * w, line[3] * h))
        eyes = _EYES.get(key)
        if eyes and blink > 0.02:                                # eyes squash shut and open again
            shape, cover, ink, boxes = eyes
            for l, t, r, b in boxes:
                rect = QRectF(l * w, t * h, (r - l) * w, (b - t) * h)
                lp.setPen(Qt.NoPen)
                lp.setBrush(QColor(*cover))
                (lp.drawEllipse if shape == "ellipse" else lp.drawRect)(rect)
                shut = rect.height() * max(0.08, 1 - blink)
                lid = QRectF(rect.left(), rect.center().y() - shut / 2, rect.width(), shut)
                lp.setBrush(QColor(*ink))
                (lp.drawEllipse if shape == "ellipse" else lp.drawRect)(lid)

        lp.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        y = int(((self._angle / 360.0 * 1.6) % 1.0) * (h + 40)) - 20      # a faint scan line
        lp.fillRect(0, y, w, 2, QColor(255, 255, 255, 38))
        lp.fillRect(0, y + 2, w, 10, QColor(accent.red(), accent.green(), accent.blue(), 16))
        # soften the edges so the picture melts into the screen instead of showing its rectangle
        lp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        lp.translate(w / 2.0, h / 2.0)
        lp.scale(w / 2.0, h / 2.0)
        fade = QRadialGradient(0.0, 0.0, 1.0)
        fade.setColorAt(0.0, QColor(0, 0, 0, 255))
        fade.setColorAt(0.78, QColor(0, 0, 0, 255))
        fade.setColorAt(1.0, QColor(0, 0, 0, 0))
        lp.fillRect(QRectF(-1.0, -1.0, 2.0, 2.0), QBrush(fade))
        lp.end()

        # a hologram shimmers; every few seconds it glitches for a blink: a band slips sideways
        opacity = 1.0
        if key in _FLICKER:
            opacity = 0.9 + 0.1 * math.sin(now * 37) * math.sin(now * 11)
        painter.setOpacity(opacity)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.save()
        painter.translate(cx, cy)
        tilt = math.sin(now * 0.9) * 1.1 + (math.sin(now * 5.5) * 1.6 * mouth_v if speaking else 0.0)
        painter.rotate(tilt)                                     # a gentle sway, and a nod while speaking
        gl = key in _FLICKER and int(now * 3) % 9 == 0 and (now * 3) % 1 < 0.12
        if gl:
            band_y = int(((now * 7) % 1.0) * h * 0.8)
            band_h = max(6, h // 12)
            painter.drawPixmap(int(-w / 2), int(-h / 2), layer, 0, 0, w, band_y)
            painter.drawPixmap(int(-w / 2 + w * 0.03), int(-h / 2 + band_y), layer, 0, band_y, w, band_h)
            painter.drawPixmap(int(-w / 2), int(-h / 2 + band_y + band_h), layer, 0, band_y + band_h, w, h - band_y - band_h)
        else:
            painter.drawPixmap(int(-w / 2), int(-h / 2), layer)
        painter.restore()
        painter.setOpacity(1.0)

    def set_tint(self, colours) -> None:
        self._tint = colours
        self.update()

    def set_ultron(self, on: bool) -> None:
        if on != self._ultron:
            self._ultron = on
            self.update()

    def set_jarvis(self, on: bool) -> None:
        """Jarvis look: the whole core turns gold instead of red + blue."""
        if on != self._jarvis:
            self._jarvis = on
            self.update()

    # -- animation --------------------------------------------------------
    def _speed_for_state(self) -> float:
        """Degrees advanced per tick — busier states spin/pulse faster."""
        return {
            AIState.IDLE: 0.4,
            AIState.LISTENING: 1.6,
            AIState.THINKING: 2.2,
            AIState.PROCESSING: 2.6,
            AIState.EXECUTING: 3.2,
            AIState.SPEAKING: 2.0,
            AIState.ERROR: 0.2,
        }.get(self._state, 0.5)

    def _tick(self) -> None:
        self._angle = (self._angle + self._speed_for_state()) % 360
        self._pulse_phase = (self._pulse_phase + 0.02) % 1.0
        self.update()

    # -- painting ---------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802 (Qt naming convention)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)

            w, h = self.width(), self.height()
            size = min(w, h) - 20
            cx, cy = w / 2, h / 2
            radius = size / 2

            accent, red, blue = self.palette_colors()

            if self._face is not None:
                self._draw_face(painter, cx, cy, radius, accent)
            else:
                self._draw_web(painter, cx, cy, radius, accent)
                self._draw_beams(painter, cx, cy, radius, red, blue)
                self._draw_orbit_rings(painter, cx, cy, radius, red, blue)
                self._draw_core(painter, cx, cy, radius, accent)
        finally:
            # Guarantees the painter is always closed, even if something
            # above raises (e.g. the process gets interrupted mid-frame) —
            # an unclosed painter is what causes Qt's endless
            # "QBackingStore::endPaint() called with active painter"
            # warning spam.
            painter.end()

    def _draw_web(self, painter, cx, cy, radius, accent):
        """Faint rotating web: a few concentric circles crossed by radial
        spokes, like a spiderweb — sits behind everything else."""
        web_color = QColor(accent)
        web_color.setAlpha(45)
        pen = QPen(web_color, 1)
        painter.setPen(pen)

        # Concentric circles
        for frac in (0.35, 0.6, 0.85, 1.05):
            r = radius * frac
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # Radial spokes, slowly counter-rotating
        spoke_angle = -self._angle * 0.3
        spoke_count = 8
        for i in range(spoke_count):
            a = math.radians(spoke_angle + i * (360 / spoke_count))
            x2 = cx + radius * 1.05 * math.cos(a)
            y2 = cy + radius * 1.05 * math.sin(a)
            painter.drawLine(QPointF(cx, cy), QPointF(x2, y2))

    def _draw_beams(self, painter, cx, cy, radius, red, blue):
        """Two long diagonal beams crossing through the center, like laser
        lines, rotating slowly in opposite directions."""
        beam_len = radius * 1.35

        def draw_beam(angle_deg, color, width):
            a = math.radians(angle_deg)
            dx, dy = math.cos(a) * beam_len, math.sin(a) * beam_len
            c = QColor(color)
            c.setAlpha(190)
            pen = QPen(c, width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(cx - dx, cy - dy), QPointF(cx + dx, cy + dy))

        draw_beam(self._angle * 1.1 + 20, red, 2)
        draw_beam(-self._angle * 0.9 - 20, blue, 2)

    def _draw_orbit_rings(self, painter, cx, cy, radius, red, blue):
        """Several tilted elliptical rings spinning at different speeds/
        sizes, crossing each other like orbiting bands around an atom."""

        def draw_ring(angle_deg, tilt_deg, color, squash, size_frac, width, alpha):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle_deg)
            c = QColor(color)
            c.setAlpha(alpha)
            pen = QPen(c, width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.scale(1.0, squash)
            painter.rotate(tilt_deg)
            painter.drawEllipse(QPointF(0, 0), radius * size_frac, radius * size_frac)
            painter.restore()

        # Main large rings (bold, opposite spin)
        draw_ring(self._angle, 15, red, 0.45, 0.92, 5, 210)
        draw_ring(-self._angle * 1.15, -15, blue, 0.45, 0.92, 5, 210)

        # Extra mid-size rings, different tilt/speed, slightly fainter
        draw_ring(-self._angle * 0.7 + 60, 55, red, 0.65, 0.72, 3, 150)
        draw_ring(self._angle * 0.85 - 60, -55, blue, 0.65, 0.72, 3, 150)

        # Small fast inner rings for extra depth
        draw_ring(self._angle * 1.6, 35, red, 0.3, 0.42, 2, 170)
        draw_ring(-self._angle * 1.8, -35, blue, 0.3, 0.42, 2, 170)

    def _draw_core(self, painter, cx, cy, radius, accent):
        """Bright pulsing point where everything crosses."""
        pulse = 0.5 + 0.5 * math.sin(self._pulse_phase * 2 * math.pi)

        # Soft glow halo
        glow = QColor(accent)
        glow.setAlpha(60)
        glow_r = radius * 0.22 + pulse * 10
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # Bright center point
        core_color = QColor(accent).lighter(130)
        core_color.setAlpha(230)
        inner_radius = radius * 0.08 + pulse * 3
        painter.setBrush(core_color)
        painter.drawEllipse(QPointF(cx, cy), inner_radius, inner_radius)
