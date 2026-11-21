"""
ui/compose_dialog.py
----------------------
The form that opens when you press WHATSAPP, EMAIL or MESSAGE PHONE in EV ACTIONS: it asks who, and what to say,
then sends. Pressing Send in this window is your confirmation.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout

from ui.theme import dialog_stylesheet

_KINDS = {
    "whatsapp": ("Send a WhatsApp message", "To  (a saved name, or a phone number with country code, e.g. +91 98765 43210)",
                 "Remember this number as (optional name)", False),
    "email": ("Send an email", "To  (a saved contact, or an email address)", "", True),
    "phone": ("Message my phone", "", "", False),
}


class ComposeDialog(QDialog):
    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        title, to_label, save_label, has_subject = _KINDS[kind]
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.setStyleSheet(dialog_stylesheet())
        lay = QVBoxLayout(self)
        head = QLabel(title.upper())
        head.setObjectName("SectionTitle")
        lay.addWidget(head)
        self.to = QLineEdit()
        self.save_as = QLineEdit()
        self.subject = QLineEdit()
        if to_label:
            lay.addWidget(QLabel(to_label))
            lay.addWidget(self.to)
        if save_label:
            lay.addWidget(QLabel(save_label))
            lay.addWidget(self.save_as)
        if has_subject:
            lay.addWidget(QLabel("Subject"))
            lay.addWidget(self.subject)
        lay.addWidget(QLabel("Message"))
        self.body = QTextEdit()
        self.body.setMinimumHeight(110)
        self.body.setAcceptRichText(False)
        lay.addWidget(self.body)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #E8A0A0;")
        lay.addWidget(self.note)
        send = QPushButton("SEND")
        send.setMinimumHeight(38)
        send.setDefault(True)
        send.clicked.connect(self._ok)
        lay.addWidget(send)

    def _ok(self) -> None:
        if self.kind != "phone" and not self.to.text().strip():
            self.note.setText("Who should it go to?")
            return
        if not self.body.toPlainText().strip():
            self.note.setText("Write the message first.")
            return
        self.accept()

    def values(self) -> dict:
        return {"to": self.to.text().strip(), "save_as": self.save_as.text().strip(),
                "subject": self.subject.text().strip(), "message": self.body.toPlainText().strip()}
