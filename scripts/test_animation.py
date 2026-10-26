"""Play just the startup transition, over a small test window with the real centre core.

Run (from the EV_AI folder):
    venv\\Scripts\\python.exe scripts\\test_animation.py

Press R in the test window to replay, Esc to quit.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget  # noqa: E402

from core import user_prefs  # noqa: E402
from ui.animations import AICoreWidget  # noqa: E402
from ui.theme import apply_theme  # noqa: E402
from ui.transition import play_startup_transition  # noqa: E402


class Demo(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EV AI - transition test  (R = replay, Esc = quit)")
        self.setObjectName("RootBackground")
        self.resize(1180, 720)
        central = QWidget()
        central.setObjectName("RootBackground")
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignCenter)
        self.ai_core = AICoreWidget()
        self.ai_core.setFixedSize(300, 300)
        layout.addWidget(self.ai_core, alignment=Qt.AlignCenter)
        caption = QLabel("SYSTEM ONLINE")
        caption.setAlignment(Qt.AlignCenter)
        layout.addWidget(caption)
        self.setCentralWidget(central)
        self._intro = None

    def play(self):
        self._intro = play_startup_transition(self)
        print("Started." if self._intro else "FAILED - see data/animation_error.log")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_R:
            self.play()
        elif event.key() == Qt.Key_Escape:
            QApplication.quit()


app = QApplication(sys.argv)
apply_theme(app, user_prefs.get("theme"))
win = Demo()
win.show()
QTimer.singleShot(600, win.play)
sys.exit(app.exec())
