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
from PySide6.QtCore import Qt, QTimer, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget

from core.state import AIState
from ui import theme as _theme


class AICoreWidget(QWidget):
    """Custom-painted animated indicator representing EV's current state."""

    state_changed = Signal(AIState)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 160)
        self._state = AIState.IDLE
        self._angle = 0.0          # base rotation angle, degrees
        self._pulse_phase = 0.0    # 0..1 pulse cycle position
        self._jarvis = False       # all-yellow look when Jarvis is switched on

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
        return accent, red, blue

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
