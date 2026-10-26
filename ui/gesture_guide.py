"""Gesture cheat-sheet: a small window listing every hand gesture and what it
does. Opens by itself the first time Video mode is turned on, and any time from
Settings > Gesture control > Show gesture guide."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from core import user_prefs
from ui.theme import dialog_stylesheet

GUIDE_HTML = (
    "<b>Two hands</b><br>"
    "• Move your hands toward each other → zoom in<br>"
    "• Move your hands apart → zoom out<br>"
    "• Swipe both hands left together → next virtual desktop (Win+Ctrl+Right)<br>"
    "• Swipe both hands right together → previous virtual desktop (Win+Ctrl+Left)<br>"
    "<b>One hand</b><br>"
    "• Swipe left → next Chrome tab (Ctrl+Tab)<br>"
    "• Swipe right → previous tab (Ctrl+Shift+Tab)<br>"
    "• Move your hand up → volume up; down → volume down<br>"
    "• Hold 1 finger → Win+1; 2 fingers → Win+2; 3 fingers → Win+3 (taskbar apps 1–3)<br>"
    "• Hold an open palm still, facing the camera → pause gestures<br>"
    "• While paused, hold a fist (or an open palm, see Settings) → resume"
)


class GestureGuide(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gesture guide")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedWidth(430)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel("HAND GESTURES")
        title.setProperty("role", "section")
        layout.addWidget(title)
        body = QLabel(GUIDE_HTML)
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        layout.addWidget(body)
        tip = QLabel("Keep your hand(s) in view, about an arm's length from the webcam, in good light. "
                     "Tune everything in Settings → Gesture control.")
        tip.setWordWrap(True)
        tip.setProperty("role", "sub")
        layout.addWidget(tip)
        ok = QPushButton("Got it")
        ok.clicked.connect(self.close)
        layout.addWidget(ok)
