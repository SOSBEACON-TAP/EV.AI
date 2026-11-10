"""Baymax's care dashboard: today's wellness overview, quick logging (also for numbers you read off your watch),
trusted contacts and the emergency button."""
from __future__ import annotations

import urllib.parse
import webbrowser

from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

from core import baymax


class BaymaxDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Baymax: your care dashboard")
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("<b>TODAY</b>"))
        self.summary = QLabel()
        root.addWidget(self.summary)

        row = QHBoxLayout()
        for text, kind in (("+ Glass of water", "water"), ("+ Took a break", "break")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, k=kind: self._add(k))
            row.addWidget(b)
        root.addLayout(row)

        root.addWidget(QLabel("<b>FROM YOUR WATCH</b><br><small>Noise, NoiseFit and most watches can't be read "
                              "automatically. Type the numbers from the watch app here.</small>"))
        form = QFormLayout()
        self.hr, self.steps, self.sleep = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        self.hr.setRange(0, 250)
        self.steps.setRange(0, 100000)
        self.steps.setDecimals(0)
        self.sleep.setRange(0, 24)
        self.sleep.setSingleStep(0.5)
        form.addRow("Heart rate (bpm)", self.hr)
        form.addRow("Steps today", self.steps)
        form.addRow("Sleep last night (h)", self.sleep)
        root.addLayout(form)
        save = QPushButton("Save these numbers")
        save.clicked.connect(self._save_numbers)
        root.addWidget(save)

        root.addWidget(QLabel("<b>TRUSTED PEOPLE</b><br><small>Email addresses, separated by commas (up to 5).</small>"))
        self.contacts = QLineEdit(", ".join(baymax.contacts()))
        self.contacts.editingFinished.connect(
            lambda: baymax.set_contacts([c for c in self.contacts.text().replace(";", ",").split(",")]))
        root.addWidget(self.contacts)
        sos = QPushButton("EMERGENCY: tell my trusted people")
        sos.setStyleSheet("QPushButton { background: #B00020; color: white; font-weight: 700; padding: 8px; }")
        sos.clicked.connect(self._emergency)
        root.addWidget(sos)
        root.addWidget(QLabel(f"<small>{baymax.EMERGENCY_NUMBERS}</small>"))
        self._refresh()

    def _refresh(self) -> None:
        self.summary.setText(baymax.overview().replace("\n", "<br>"))

    def _add(self, kind: str) -> None:
        baymax.log(kind)
        self._refresh()

    def _save_numbers(self) -> None:
        if self.hr.value() > 0:
            baymax.log("heart_rate", self.hr.value())
        if self.steps.value() > 0:
            baymax.log("steps", self.steps.value())
        if self.sleep.value() > 0:
            baymax.log("sleep_hours", self.sleep.value())
        self._refresh()

    def _emergency(self) -> None:
        baymax.set_contacts(self.contacts.text().replace(";", ",").split(","))
        people = baymax.contacts()
        if people:      # opens your mail app with the message ready: you press send
            q = urllib.parse.urlencode({"subject": "I need help, please call me now",
                                        "body": "This is an emergency message from EV AI (Baymax). Please contact me right away."},
                                       quote_via=urllib.parse.quote)
            webbrowser.open("mailto:" + ",".join(people) + "?" + q)
        self.summary.setText(f"<b>If this is an emergency, call now.</b><br>{baymax.EMERGENCY_NUMBERS}"
                             + ("<br>Your mail app opened with a message ready to send." if people else
                                "<br>Add trusted email addresses above to message them too."))
