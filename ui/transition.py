"""Startup hand-off animation — the logo merges into the app's centre core.

When the loading screen finishes, the app window is covered by a dark veil and the
*real* core geometry (the same red/blue rings, beams
and cyan dot that live in the middle of the app) fades in huge, then slowly shrinks and
glides into the exact spot and size of the live core while the veil fades out.
Because the animated core is drawn by the very same code as the live one and
stays in phase with it, the last frame is identical to the live widget — the
hand-off is seamless, nothing pops.

About 5 seconds, on purpose. Purely cosmetic and failsafe: any error just skips it.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

_LOGO = Path(__file__).resolve().parent.parent / "assets" / "icons" / "ev_logo.png"

_DURATION_MS = 5400
_HOLD = 0.06        # the big core holds for this share of the timeline
_SHRINK_END = 0.90  # shrinking finishes here; the last stretch sits exactly on the live core


def _log_error(where: str) -> None:
    """Never break startup, but leave a trace in data/animation_error.log."""
    try:
        import traceback
        log = Path(__file__).resolve().parent.parent / "data" / "animation_error.log"
        log.parent.mkdir(exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {where}\n{traceback.format_exc()}\n")
    except Exception:
        pass


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class LogoIntroTransition(QWidget):
    """A see-through top-level window laid exactly over the app window (the mechanism
    the very first animation used). Transparent to the mouse, follows the app window."""

    def __init__(self, window, core, on_done=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._window = window
        self._core = core                      # the live AICoreWidget (may be None)
        self._t = 0.0
        self._on_done = on_done
        self._ease = QEasingCurve(QEasingCurve.InOutCubic)
        self._logo = QPixmap(str(_LOGO))
        if self._logo.isNull():
            raise RuntimeError(f"logo image missing: {_LOGO}")

        # A private, never-shown copy of the core widget: we borrow its drawing code so the
        # animated core looks exactly like the live one.
        from ui.animations import AICoreWidget
        self._proto = AICoreWidget()
        self._proto._timer.stop()
        try:
            from core import user_prefs
            self._proto._jarvis = bool(getattr(core, "_jarvis", False) or user_prefs.get("jarvis_ui"))
        except Exception:
            pass
        self._sync_geometry()

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_tick)
        self._last = 0.0
        self._done = False

    # -- geometry helpers ---------------------------------------------------
    def _sync_geometry(self) -> None:
        origin = self._window.mapToGlobal(QPoint(0, 0))
        self.setGeometry(QRect(origin, self._window.size()))

    def _final_radius(self) -> float:
        if self._core is not None:
            return max(30.0, (min(self._core.width(), self._core.height()) - 20) / 2.0)
        return 100.0

    def _final_centre(self) -> QPointF:
        if self._core is not None and self._core.isVisible():
            g = self._core.mapToGlobal(self._core.rect().center())
            return QPointF(g - self.geometry().topLeft())
        return QPointF(self.width() / 2, self.height() / 2)

    # -- run ------------------------------------------------------------------
    def run(self) -> None:
        self._sync_geometry()
        self.show()
        self.raise_()
        self.repaint()
        self._last = time.perf_counter()
        self._timer.start()
        print("[EV AI] Intro animation: playing")

    def _on_tick(self) -> None:
        now = time.perf_counter()
        dt = min(now - self._last, 0.05)    # never jump more than 50 ms in one frame
        self._last = now
        self._t = min(1.0, self._t + dt * 1000.0 / _DURATION_MS)
        self._sync_geometry()
        self.update()
        if self._t >= 1.0:
            self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        print("[EV AI] Intro animation: finished")
        self.hide()
        self.deleteLater()
        self._proto.deleteLater()
        if self._on_done:
            try:
                self._on_done()
            except Exception:
                _log_error("on_done")

    # -- drawing --------------------------------------------------------------
    def paintEvent(self, event) -> None:
        t = self._t
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            w, h = self.width(), self.height()

            # shrink progress after the hold
            p = min(1.0, max(0.0, (t - _HOLD) / (_SHRINK_END - _HOLD)))
            e = self._ease.valueForProgress(p)

            r_final = self._final_radius()
            r_big = max(w, h) * 0.60
            radius = r_big + (r_final - r_big) * e
            start = QPointF(w / 2, h / 2)
            centre = start + (self._final_centre() - start) * e

            # veil: solid at first, fades during the second half of the shrink
            veil = int(255 * (1.0 - _smooth((p - 0.35) / 0.55)))
            if veil > 0:
                painter.fillRect(self.rect(), QColor(14, 10, 2, veil) if getattr(self._proto, "_jarvis", False) else QColor(3, 6, 12, veil))

            # No logo frame any more: the animation starts straight from the big core
            # (fading in from the dark veil), then shrinks into the live core.
            logo_op = 0.0
            core_op = _smooth(t / 0.08)

            if logo_op > 0.0:
                d = radius * 2 * 0.88
                painter.save()
                painter.setOpacity(logo_op)
                painter.translate(centre)
                painter.rotate((1.0 - e) * 60.0)
                painter.drawPixmap(QRectF(-d / 2, -d / 2, d, d), self._logo, QRectF(self._logo.rect()))
                painter.restore()

            if core_op > 0.0:
                # copy the live core's phase so the last frame matches it exactly
                if self._core is not None:
                    self._proto._angle = self._core._angle
                    self._proto._pulse_phase = self._core._pulse_phase
                    self._proto._state = self._core._state
                    self._proto._jarvis = bool(getattr(self._core, "_jarvis", False) or self._proto._jarvis)
                painter.save()
                painter.setOpacity(core_op)
                painter.translate(centre)
                k = radius / r_final
                painter.scale(k, k)               # pens scale with it, like a zoom
                self._draw_core(painter, r_final)
                painter.restore()
        except Exception:
            _log_error("paintEvent")
            self._finish()
        finally:
            painter.end()

    def _draw_core(self, painter: QPainter, radius: float) -> None:
        proto = self._proto
        accent, red, blue = proto.palette_colors()   # gold when Jarvis is on, same as the live core
        proto._draw_web(painter, 0, 0, radius, accent)
        proto._draw_beams(painter, 0, 0, radius, red, blue)
        proto._draw_orbit_rings(painter, 0, 0, radius, red, blue)
        proto._draw_core(painter, 0, 0, radius, accent)


def play_startup_transition(window, on_done=None):
    """Run the animation over `window`. Returns the overlay (the caller must
    keep a reference) or None if it was skipped."""
    try:
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()   # let the main window finish its layout first
        core = getattr(window, "ai_core", None)
        if core is not None and not core.isVisible():
            core = None
        overlay = LogoIntroTransition(window, core, on_done)
        overlay.run()
        return overlay
    except Exception:
        _log_error("play_startup_transition")
        return None
