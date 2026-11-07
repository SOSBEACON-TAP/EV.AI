"""
ui/karen_panel.py
-----------------
KAREN MODE panel: visible parental controls for this PC (see core/karen.py).
The panel always shows whether Karen mode is on, today's screen time, bedtime and the rules.
Changing the rules, turning it off, or granting extra time needs the parent's PIN.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTime, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox, QTextEdit, QTimeEdit, QVBoxLayout, QWidget)

from core import karen as karenmod
from ui.widgets import HoverButton


class KarenPanel(QWidget):
    say = Signal(str)
    sites_changed = Signal(list)       # blocked websites changed (the Chrome extension needs to know)
    state_changed = Signal(bool)       # Karen mode turned on/off

    def __init__(self, karen: karenmod.Karen, parent=None):
        super().__init__(parent)
        self.k = karen
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("KAREN MODE  (parental controls)")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        self.state = QLabel("")
        self.state.setWordWrap(True)
        lay.addWidget(self.state)
        note = QLabel("Visible controls: this screen shows when Karen mode is on and what the rules are. "
                      "Changing them needs the parent's PIN.")
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 10px; opacity: 0.8;")
        lay.addWidget(note)
        self.rules_lbl = QLabel("")
        self.rules_lbl.setWordWrap(True)
        lay.addWidget(self.rules_lbl)
        for text, fn in (("TURN ON / OFF  (PIN)", self._toggle), ("SET RULES  (PIN)", self._rules),
                         ("GIVE EXTRA TIME  (PIN)", self._extra), ("USAGE REPORT", self._report), ("WEEKLY REPORT FILE", self._weekly),
                         ("CHANGE PIN  (PIN)", self._change_pin)):
            b = HoverButton(text)
            b.clicked.connect(fn)
            lay.addWidget(b)
        lay.addStretch(1)
        t = QTimer(self)
        t.timeout.connect(self.refresh)
        t.start(5000)
        self.refresh()

    def refresh(self):
        self.state.setText(self.k.status_line())
        self.state.setStyleSheet("font-weight: 700;")
        d = self.k.data
        sites = ", ".join(d["blocked_sites"]) or "none"
        apps = ", ".join(d["blocked_apps"]) or "none"
        self.rules_lbl.setText(f"Daily limit: {d['daily_limit_min'] or 'none'} min\nBedtime: " +
                               (f"{d['bed_start']} to {d['bed_end']}" if d["bed_on"] else "off") +
                               f"\nBlocked apps: {apps}\nBlocked sites (Chrome): {sites}")

    # -------------------------------------------------------------------- PIN
    def _ask_pin(self, why: str) -> bool:
        if not self.k.has_pin:
            return self._create_pin()
        left = self.k.pin_locked_for()
        if left:
            QMessageBox.warning(self, "Karen mode", f"Too many wrong tries. Try again in {left // 60 + 1} minute(s).")
            return False
        pin, ok = QInputDialog.getText(self, "Parent PIN", f"{why}\nEnter the parent PIN:", QLineEdit.Password)
        if not ok:
            return False
        if self.k.check_pin(pin):
            return True
        QMessageBox.warning(self, "Karen mode", "Wrong PIN.")
        return False

    def _create_pin(self) -> bool:
        pin, ok = QInputDialog.getText(self, "Create the parent PIN", "Choose a PIN (at least 4 digits). Keep it secret:", QLineEdit.Password)
        if not ok:
            return False
        again, ok = QInputDialog.getText(self, "Create the parent PIN", "Type it again:", QLineEdit.Password)
        if not ok or again != pin or not self.k.set_pin(pin):
            QMessageBox.warning(self, "Karen mode", "The PINs didn't match or were too short (4 or more characters).")
            return False
        return True

    def _change_pin(self):
        if self._ask_pin("Change the PIN."):
            self._create_pin()

    # ---------------------------------------------------------------- actions
    def _toggle(self):
        if not self._ask_pin("Turn Karen mode " + ("OFF." if self.k.enabled else "ON.")):
            return
        self.k.set_enabled(not self.k.enabled)
        self.refresh()
        self.state_changed.emit(self.k.enabled)
        self.sites_changed.emit(self.k.data["blocked_sites"] if self.k.enabled else [])
        self.say.emit("Karen mode is on." if self.k.enabled else "Karen mode is off.")

    def _extra(self):
        if not self._ask_pin("Give extra screen time today."):
            return
        n, ok = QInputDialog.getInt(self, "Extra time", "Extra minutes for today:", 30, 1, 480)
        if ok:
            self.k.grant_minutes(n)
            self.refresh()
            self.say.emit(f"{n} extra minutes granted.")

    def _report(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Karen mode: usage report")
        dlg.resize(460, 380)
        v = QVBoxLayout(dlg)
        box = QTextEdit()
        box.setReadOnly(True)
        box.setStyleSheet("font-family: Consolas;")
        box.setPlainText(self.k.report(7))
        v.addWidget(box)
        dlg.exec()

    def _weekly(self):
        out = self.k.write_weekly_report()
        self.k.save()
        self.say.emit(f"Weekly report saved: {out.name}")
        try:
            import os
            if os.name == "nt":
                os.startfile(str(out))
        except OSError:
            pass

    def _rules(self):
        if not self._ask_pin("Change the rules."):
            return
        d = self.k.data
        dlg = QDialog(self)
        dlg.setWindowTitle("Karen mode rules")
        dlg.resize(440, 640)
        form = QFormLayout(dlg)
        limit = QSpinBox()
        limit.setRange(0, 1440)
        limit.setValue(d["daily_limit_min"])
        limit.setSuffix(" min  (0 = no limit)")
        bed_on = QCheckBox("Lock the PC at bedtime")
        bed_on.setChecked(d["bed_on"])
        start, end = QTimeEdit(QTime.fromString(d["bed_start"], "HH:mm")), QTimeEdit(QTime.fromString(d["bed_end"], "HH:mm"))
        for t in (start, end):
            t.setDisplayFormat("HH:mm")
        apps = QPlainTextEdit("\n".join(d["blocked_apps"]))
        apps.setPlaceholderText("one program per line, e.g. game.exe")
        sites = QPlainTextEdit("\n".join(d["blocked_sites"]))
        sites.setPlaceholderText("one website per line, e.g. youtube.com")
        form.addRow("Daily screen time", limit)
        form.addRow(bed_on)
        form.addRow("Bedtime starts", start)
        form.addRow("Bedtime ends", end)
        form.addRow("Blocked programs (closed when opened)", apps)
        form.addRow("Blocked websites (Chrome + EV AI extension)", sites)
        allow_on = QCheckBox("Allow ONLY the websites below (blocks all others, for younger children)")
        allow_on.setChecked(d.get("allow_only", False))
        allowed = QPlainTextEdit("\n".join(d.get("allowed_sites", [])))
        allowed.setPlaceholderText("one website per line, e.g. wikipedia.org")
        form.addRow(allow_on)
        form.addRow("Allowed websites", allowed)
        save = QPushButton("Save rules")
        save.clicked.connect(dlg.accept)
        form.addRow(save)
        if dlg.exec():
            try:
                self.k.set_rules(limit.value(), bed_on.isChecked(), start.time().toString("HH:mm"), end.time().toString("HH:mm"),
                                 apps.toPlainText().splitlines(), sites.toPlainText().splitlines(),
                                 allow_on.isChecked(), allowed.toPlainText().splitlines())
            except ValueError:
                QMessageBox.warning(self, "Karen mode", "Those times don't look right.")
                return
            self.refresh()
            self.sites_changed.emit(self.k.data["blocked_sites"] if self.k.enabled else [])
            self.say.emit("Rules saved.")
