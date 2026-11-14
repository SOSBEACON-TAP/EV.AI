"""EDITH's Ctrl + hover: while EDITH is on, hold Ctrl and point at anything in EV AI - a small panel tells you what it is
and what it does. Works on every window of the app (the main window and the HUD)."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QLabel, QWidget

# What well-known controls do, found by words in their label (first match wins).
_KNOWN = [
    ("start voice", "Turns the microphone on so EV hears you say 'Hey EV'."),
    ("stop voice", "Turns the microphone off."),
    ("stop", "Stops whatever EV is saying or doing right now."),
    ("send", "Sends what you typed to EV."),
    ("mode:", "Opens the mode wheel (Ctrl+M) to switch between EV, Jarvis, Ultron, Edith and the others."),
    ("edith", "Edith watches your screen now and then and speaks up when something is worth mentioning. Click her glasses to turn the HUD on or off."),
    ("video", "Video mode: control a video with hand gestures through the camera."),
    ("song", "Song mode: the sound player."),
    ("settings", "Opens Settings: theme, keys, voice, email, updates and more."),
    ("memory", "Shows what EV has remembered."),
    ("internet", "Shows whether EV can reach the internet."),
    ("cpu", "How busy your processor is right now."),
    ("ram", "How much memory is in use right now."),
    ("last heard", "The last thing the microphone heard."),
    ("overdrive", "Overdrive: every important tool at once, brighter and faster for 90 seconds, then it burns out and cools down."),
]


def describe(widget: QWidget | None) -> str:
    """The best explanation we have for this widget, climbing up its parents until one has something to say."""
    w = widget
    while w is not None:
        info = w.property("evInfo")
        if info:
            return str(info)
        label = ""
        for attr in ("text", "placeholderText"):
            fn = getattr(w, attr, None)
            if callable(fn):
                try:
                    label = (fn() or "").strip()
                except Exception:
                    label = ""
            if label:
                break
        low = label.lower()
        for key, text in _KNOWN:
            if key in low:
                return f"{label.strip()}\n{text}"
        tip = w.toolTip() if hasattr(w, "toolTip") else ""
        if tip:
            return f"{label}\n{tip}".strip()
        if label and w.metaObject().className() in ("QPushButton", "QToolButton", "QLabel", "QCheckBox", "QRadioButton"):
            return f"{label}\n({w.metaObject().className()[1:].lower()})"
        w = w.parentWidget()
    return ""


class HoverInfo(QObject):
    """Install once. `enabled` is called each time to ask whether EDITH is on."""

    def __init__(self, enabled):
        super().__init__()
        self._enabled = enabled
        self._panel = QLabel()
        self._panel.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._panel.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._panel.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._panel.setWordWrap(True)
        self._panel.setMaximumWidth(320)
        self._panel.setStyleSheet(
            "QLabel { background: rgba(8,18,34,235); color: #BFDDFF; border: 1px solid #4DA3FF; border-radius: 8px; "
            "padding: 8px 10px; font-size: 12px; }")
        self._last = ""
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        t = event.type()
        if t in (QEvent.MouseMove, QEvent.KeyPress, QEvent.KeyRelease):
            try:
                if not self._enabled() or not (QApplication.keyboardModifiers() & Qt.ControlModifier):
                    self._hide()
                    return False
                pos = QCursor.pos()
                w = QApplication.widgetAt(pos)
                if w is None or w is self._panel:
                    self._hide()
                    return False
                text = describe(w)
                if not text:
                    self._hide()
                    return False
                if text != self._last:
                    self._last = text
                    first, _, rest = text.partition("\n")
                    self._panel.setText(f"<b>{first}</b>" + (f"<br>{rest}" if rest else ""))
                    self._panel.adjustSize()
                self._panel.move(pos + QPoint(16, 18))
                self._panel.show()
            except Exception:
                self._hide()
        return False

    def _hide(self) -> None:
        self._last = ""
        if self._panel.isVisible():
            self._panel.hide()
