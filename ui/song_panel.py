"""
ui/song_panel.py
------------------
Song mode: a small always-on-top music remote. Type a song or artist and
press Play to open it on YouTube; the buttons send the system media keys
(previous / play-pause / next, volume, mute), which work with whatever
player is active — YouTube in a browser, Spotify, Windows media player.
Closing the panel turns Song mode off.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from tools import media as media_tools
from tools import browser as browser_tools

_STYLE = """
QWidget#SongPanel { background: #0b121c; border: 1px solid #1f6f8b; border-radius: 12px; }
QLabel { color: #cfe9f3; background: transparent; }
QLabel#SongTitle { color: #5fd0e8; font-weight: bold; letter-spacing: 2px; }
QLabel#SongStatus { color: #8fb3c2; font-size: 11px; }
QLineEdit { background: #101c2a; color: #e8f6fc; border: 1px solid #1f6f8b;
            border-radius: 6px; padding: 6px 8px; }
QPushButton { background: #12263a; color: #e8f6fc; border: 1px solid #1f6f8b;
              border-radius: 6px; padding: 6px 10px; }
QPushButton:hover { background: #1b3a55; }
QPushButton#SongClose { border: none; background: transparent; color: #8fb3c2; padding: 2px 6px; }
"""


class SongPanel(QWidget):
    closed = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setObjectName("SongPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_STYLE)
        self.setFixedWidth(330)
        self._drag_offset = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("🎵 SONG MODE")
        title.setObjectName("SongTitle")
        close = QPushButton("✕")
        close.setObjectName("SongClose")
        close.clicked.connect(self.close)
        shrink = QPushButton("—")
        shrink.setObjectName("SongClose")
        shrink.setToolTip("Shrink / expand")
        shrink.clicked.connect(self._toggle_shrink)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(shrink)
        top.addWidget(close)
        root.addLayout(top)

        row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("Song or artist…")
        self._query.returnPressed.connect(self._play)
        play = QPushButton("▶ Play")
        play.clicked.connect(self._play)
        row.addWidget(self._query, 1)
        row.addWidget(play)
        root.addLayout(row)

        controls = QHBoxLayout()
        for text, func in (("⏮", media_tools.previous_track), ("⏯", media_tools.play_pause),
                           ("⏭", media_tools.next_track), ("🔉", media_tools.volume_down),
                           ("🔊", media_tools.volume_up), ("🔇", media_tools.mute)):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, f=func: self._press(f))
            controls.addWidget(button)
        root.addLayout(controls)

        self._status = QLabel("Opens the search on YouTube — pick a result to start it.")
        self._status.setObjectName("SongStatus")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._body = [row, controls]
        self._shrunk = False

    def _toggle_shrink(self) -> None:
        """Collapse to just the title bar (or expand back)."""
        self._shrunk = not self._shrunk
        for layout in self._body:
            for i in range(layout.count()):
                item = layout.itemAt(i).widget()
                if item is not None:
                    item.setVisible(not self._shrunk)
        self._status.setVisible(not self._shrunk)
        self.adjustSize()

    def show_at_corner(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.right() - self.width() - 28, screen.bottom() - self.height() - 28)
        self.show()
        self.raise_()
        self._query.setFocus()

    def _play(self) -> None:
        query = self._query.text().strip()
        if not query:
            return
        result = browser_tools.search_youtube(query)
        self._status.setText(result.get("error") or f"Searching YouTube for “{query}”…")

    def _press(self, func) -> None:
        result = func()
        if isinstance(result, dict) and result.get("error"):
            self._status.setText(result["error"])

    # frameless -> drag by the background
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
