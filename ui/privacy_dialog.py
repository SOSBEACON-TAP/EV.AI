"""
ui/privacy_dialog.py
----------------------
Privacy center (Settings -> Privacy center): one place to see what EV.AI
can currently hear, see and reach — microphone / camera / screen status,
which outside services it talks to, what it stores on this PC, which
actions always ask first — plus a history of what it has actually done.
Read-only apart from "Clear history".
"""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from config import settings, APP_ROOT
from core import audit_log, user_prefs
from ui.settings_dialog import _divider, _note_label, _section_title
from ui.theme import dialog_stylesheet


def _row(label: str, value: str, on: bool | None = None) -> QWidget:
    """One 'label ...... value' line; `on` colours the value (green = on/in use)."""
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    name = QLabel(label)
    status = QLabel(value)
    status.setWordWrap(True)
    status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if on is True:
        status.setStyleSheet("color: #e0a040; font-weight: bold;")   # amber: something is active
    elif on is False:
        status.setStyleSheet("color: #5fc78a;")                       # green: nothing active
    layout.addWidget(name, 1)
    layout.addWidget(status, 1)
    return box


class PrivacyDialog(QDialog):
    def __init__(self, window=None):
        super().__init__(window)
        self._window = window
        self.setWindowTitle(f"{settings.APP_NAME} — Privacy center")
        self.setFixedWidth(430)
        self.setMaximumHeight(680)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._body = QWidget()
        scroll.setWidget(self._body)
        outer.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(20, 0, 20, 0)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._rebuild)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(refresh)
        buttons.addWidget(close)
        outer.addLayout(buttons)

        self._rebuild()
        timer = QTimer(self)             # live status while the window is open
        timer.timeout.connect(self._rebuild)
        timer.start(4000)

    # -- content -------------------------------------------------------------
    def _snapshot(self) -> dict:
        try:
            return self._window.privacy_snapshot()
        except Exception:
            return {}

    def _rebuild(self) -> None:
        snap = self._snapshot()
        old = self._body.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            QWidget().setLayout(old)   # detach so a fresh layout can be installed
        root = QVBoxLayout(self._body)
        root.setContentsMargins(20, 18, 20, 8)
        root.setSpacing(6)

        # -- right now -------------------------------------------------------
        root.addWidget(_section_title("RIGHT NOW"))
        mic = snap.get("mic", "Unknown")
        root.addWidget(_row("Microphone", mic, on=mic.lower().startswith(("listening", "clap"))))
        cam = snap.get("camera", "Unknown")
        root.addWidget(_row("Camera", cam, on=cam.lower().startswith("in use")))
        screen = snap.get("screen", "Unknown")
        root.addWidget(_row("Screen capture", screen, on=screen.lower().startswith("on")))
        root.addWidget(_note_label("Amber = active at this moment. Voice, camera and screen "
                                   "features are all off until you turn them on or speak."))
        root.addWidget(_divider())

        # -- services --------------------------------------------------------
        root.addWidget(_section_title("CONNECTED SERVICES"))
        provider = (settings.AI_PROVIDER or "—").title()
        key_state = "key saved" if settings.AI_API_KEY else "no key"
        root.addWidget(_row("AI provider", f"{provider} ({key_state})"))
        root.addWidget(_note_label("What you type or say to EV is sent to this provider to get a "
                                   "reply. Screenshots are sent only while Observe is on, or when "
                                   "you attach an image."))
        email = settings.EMAIL_ADDRESS or "not set up"
        root.addWidget(_row("Email account", email))
        wa = settings.whatsapp_profile_path
        root.addWidget(_row("WhatsApp / browser login", "saved on this PC" if wa.exists() else "none saved"))
        root.addWidget(_divider())

        # -- permissions -----------------------------------------------------
        root.addWidget(_section_title("ALWAYS ASKS FIRST"))
        tools = snap.get("confirm_tools") or []
        root.addWidget(_note_label(
            ", ".join(t.replace("_", " ") for t in tools) if tools else "—"))
        root.addWidget(_note_label("These actions are blocked until you explicitly say yes, "
                                   "in every mode — including Automatic."))
        root.addWidget(_divider())

        # -- local data ------------------------------------------------------
        root.addWidget(_section_title("STORED ON THIS PC"))
        for label, path in (
            ("Settings", APP_ROOT / "data" / "user_prefs.json"),
            ("To-dos, notes, reminders", APP_ROOT / "data" / "personal.json"),
            ("Contacts", APP_ROOT / "data" / "contacts.json"),
            ("Memory database", settings.db_file),
            ("Action history", APP_ROOT / "data" / "automation_history.jsonl"),
            ("API keys & email password", APP_ROOT / ".env"),
        ):
            root.addWidget(_row(label, "yes" if path.exists() else "—"))
        open_btn = QPushButton("Open data folder")
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_ROOT / "data"))))
        root.addWidget(open_btn)
        root.addWidget(_note_label("Keys live in the .env file next to the app, never in the code. "
                                   "Nothing is sent anywhere except the services above."))
        root.addWidget(_divider())

        # -- history ---------------------------------------------------------
        root.addWidget(_section_title("WHAT EV HAS DONE"))
        entries = audit_log.recent(40)
        if not entries:
            root.addWidget(_note_label("Nothing yet."))
        for entry in entries:
            when = datetime.fromtimestamp(entry["t"]).strftime("%d %b %H:%M")
            mark = "✓" if entry.get("ok") else "✗"
            detail = f" — {entry['args']}" if entry.get("args") else ""
            note = f"  ({entry['note']})" if entry.get("note") else ""
            line = QLabel(f"{mark} {when}  {entry['tool'].replace('_', ' ')}{detail}{note}")
            line.setWordWrap(True)
            line.setProperty("role", "sub")
            root.addWidget(line)
        clear = QPushButton("Clear history")
        clear.clicked.connect(self._clear_history)
        root.addWidget(clear)
        root.addStretch(1)

    def _clear_history(self) -> None:
        audit_log.clear()
        self._rebuild()
