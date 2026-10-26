"""
ui/widgets.py
--------------
Custom widgets shared across the EV AI dashboard.

HoverButton extends QPushButton with:
- A soft glow (QGraphicsDropShadowEffect) that animates in on hover and
  back out on leave, giving a "touch-reactive" feel.
- A short synthesized hover sound (assets/sounds/hover.wav), played via
  QSoundEffect. The sound is generated procedurally (see the project's
  build notes) — it is not sampled from any copyrighted source.

Both effects degrade gracefully: if the sound file is missing or
QtMultimedia has an issue on a given machine, the button still works
normally, it just won't make sound.
"""

from pathlib import Path

from PySide6.QtCore import QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect

try:
    from PySide6.QtMultimedia import QSoundEffect
    _MULTIMEDIA_AVAILABLE = True
except ImportError:
    _MULTIMEDIA_AVAILABLE = False

_SOUND_PATH = Path(__file__).resolve().parent.parent / "assets" / "sounds" / "hover.wav"
_GLOW_COLOR = QColor("#5FD0E8")

# Settings -> "Play a soft sound when hovering buttons". Module-level so one
# switch covers every HoverButton instantly, without re-reading the prefs file.
_hover_sound_on = True


def set_hover_sound_enabled(enabled: bool) -> None:
    global _hover_sound_on
    _hover_sound_on = bool(enabled)


try:
    from core import user_prefs as _prefs
    _hover_sound_on = bool(_prefs.get("hover_sound"))
except Exception:
    pass


class HoverButton(QPushButton):
    """A QPushButton that glows and (optionally) makes a soft sound on hover."""

    def __init__(self, text: str = "", parent=None, sound_enabled: bool = True):
        super().__init__(text, parent)

        # Glow effect, starts invisible (blurRadius 0)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setColor(_GLOW_COLOR)
        self._glow.setOffset(0, 0)
        self._glow.setBlurRadius(0)
        self.setGraphicsEffect(self._glow)

        self._anim = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._sound = None
        if sound_enabled and _MULTIMEDIA_AVAILABLE and _SOUND_PATH.exists():
            try:
                self._sound = QSoundEffect(self)
                self._sound.setSource(QUrl.fromLocalFile(str(_SOUND_PATH)))
                self._sound.setVolume(0.3)
            except Exception:
                # Never let a broken audio backend take down the UI.
                self._sound = None

    def _animate_glow(self, target: float):
        self._anim.stop()
        self._anim.setStartValue(self._glow.blurRadius())
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event):
        self._animate_glow(24)
        if _hover_sound_on and self._sound is not None and self._sound.isLoaded():
            self._sound.play()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_glow(0)
        super().leaveEvent(event)
