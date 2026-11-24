"""
ui/contacts_dialog.py
-----------------------
SAVED CONTACTS and CALL PHONE (EV ACTIONS).

SAVED CONTACTS is the address book EV uses everywhere: "email Mom", "WhatsApp Mom", "call Mom". Each person has a name, a phone
number with country code and/or an email address. CALL PHONE picks a saved contact (or a typed number); the call is placed by the
connected phone, which shows a call card you tap (see tools/phone_call.py).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from core import user_prefs
from tools import contacts
from ui.theme import dialog_stylesheet


def _line(c: dict) -> str:
    bits = [b for b in (c.get("phone"), c.get("email")) if b]
    return c["name"] + ("   -   " + "   ".join(bits) if bits else "")


class ContactsDialog(QDialog):
    """List, add, edit and delete contacts. CALL / WHATSAPP / EMAIL on the chosen person are handed to the main window."""
    action = Signal(str, str)          # "call" | "whatsapp" | "email", contact name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Saved contacts")
        self.setMinimumSize(520, 520)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        self._editing = ""             # the saved name being edited ("" = a new contact)
        lay = QVBoxLayout(self)
        head = QLabel("SAVED CONTACTS")
        head.setObjectName("SectionTitle")
        lay.addWidget(head)
        hint = QLabel("EV uses these when you say \"call Mom\", \"WhatsApp Mom\" or \"email Mom\". Click a person to edit them.")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search")
        self.search.textChanged.connect(self._fill)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMinimumHeight(170)
        self.list.currentItemChanged.connect(self._picked)
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        for text, kind in (("CALL", "call"), ("WHATSAPP", "whatsapp"), ("EMAIL", "email")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, k=kind: self._act(k))
            row.addWidget(b)
        lay.addLayout(row)

        self.form_title = QLabel("New contact")
        self.form_title.setObjectName("SectionTitle")
        lay.addWidget(self.form_title)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name, for example Mom")
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("Phone with country code, for example +91 98765 43210")
        self.email = QLineEdit()
        self.email.setPlaceholderText("Email (optional)")
        for w in (self.name, self.phone, self.email):
            lay.addWidget(w)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #E8A0A0;")
        lay.addWidget(self.note)
        row2 = QHBoxLayout()
        save = QPushButton("SAVE")
        save.setDefault(True)
        save.clicked.connect(self._save)
        new = QPushButton("NEW")
        new.clicked.connect(self._new)
        delete = QPushButton("DELETE")
        delete.clicked.connect(self._delete)
        for b in (save, new, delete):
            row2.addWidget(b)
        lay.addLayout(row2)
        self._fill()

    # -- list ---------------------------------------------------------------
    def _fill(self, *_):
        needle = self.search.text().strip().lower()
        self.list.blockSignals(True)
        self.list.clear()
        for c in contacts.all_contacts():
            if needle and needle not in (c["name"] + c["phone"] + c["email"]).lower():
                continue
            it = QListWidgetItem(_line(c))
            it.setData(Qt.UserRole, c)
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _current(self) -> dict | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _picked(self, *_):
        c = self._current()
        if not c:
            return
        self._editing = c["name"]
        self.form_title.setText("Edit: " + c["name"])
        self.name.setText(c["name"])
        self.phone.setText(c["phone"])
        self.email.setText(c["email"])
        self.note.clear()

    def _new(self):
        self._editing = ""
        self.list.blockSignals(True)
        self.list.setCurrentRow(-1)
        self.list.blockSignals(False)
        self.form_title.setText("New contact")
        for w in (self.name, self.phone, self.email):
            w.clear()
        self.note.clear()
        self.name.setFocus()

    def _save(self):
        r = contacts.set_contact(self.name.text(), self.email.text(), self.phone.text(), old_name=self._editing)
        if "error" in r:
            self.note.setText(r["error"])
            return
        self._editing = r["name"]
        self.note.setStyleSheet("color: #8FE0A0;")
        self.note.setText(f"Saved {r['name']}.")
        self._fill()

    def _delete(self):
        name = self._editing or self.name.text().strip()
        if name and contacts.delete_contact(name):
            self._new()
            self.note.setStyleSheet("color: #8FE0A0;")
            self.note.setText(f"Deleted {name}.")
            self._fill()
        else:
            self.note.setStyleSheet("color: #E8A0A0;")
            self.note.setText("Click the person you want to delete first.")

    def _act(self, kind: str):
        c = self._current()
        if not c:
            self.note.setStyleSheet("color: #E8A0A0;")
            self.note.setText("Click a person first.")
            return
        if kind == "call" and not c["phone"]:
            self.note.setStyleSheet("color: #E8A0A0;")
            self.note.setText(f"{c['name']} has no phone number yet. Add one and press SAVE.")
            return
        if kind == "whatsapp" and not c["phone"]:
            self.note.setStyleSheet("color: #E8A0A0;")
            self.note.setText(f"{c['name']} has no phone number yet. Add one and press SAVE.")
            return
        if kind == "email" and not c["email"]:
            self.note.setStyleSheet("color: #E8A0A0;")
            self.note.setText(f"{c['name']} has no email yet. Add one and press SAVE.")
            return
        self.action.emit(kind, c["name"])


class CallDialog(QDialog):
    """Pick a saved contact (or type a number) and call it through the connected phone."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Call phone")
        self.setMinimumWidth(440)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        lay = QVBoxLayout(self)
        head = QLabel("CALL PHONE")
        head.setObjectName("SectionTitle")
        lay.addWidget(head)
        lay.addWidget(QLabel("Who do you want to call?  (pick a saved contact, or type a number with country code)"))
        self.who = QComboBox()
        self.who.setEditable(True)
        for c in contacts.all_contacts():
            if c["phone"]:
                self.who.addItem(c["name"] + "   " + c["phone"], c["name"])
        self.who.setCurrentIndex(-1)
        self.who.lineEdit().setPlaceholderText("Mom, or +91 98765 43210")
        lay.addWidget(self.who)
        info = QLabel("Your phone (the one connected to EV) shows a call screen. Tap the green button there to place the call. "
                      "EV never dials by itself.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #E8A0A0;")
        lay.addWidget(self.note)
        go = QPushButton("CALL")
        go.setMinimumHeight(38)
        go.setDefault(True)
        go.clicked.connect(self._ok)
        lay.addWidget(go)

    def target(self) -> str:
        idx = self.who.currentIndex()
        text = self.who.currentText().strip()
        if idx >= 0 and text == self.who.itemText(idx):
            return str(self.who.itemData(idx) or text)
        return text

    def _ok(self) -> None:
        t = self.target()
        if not t:
            self.note.setText("Pick a person or type a number.")
            return
        if not contacts.phone_for(t):
            self.note.setText(f"I don't have a number for '{t}'. Type a number with the country code, or save the contact first.")
            return
        self.accept()
