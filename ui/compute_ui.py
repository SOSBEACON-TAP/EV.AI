"""
ui/compute_ui.py
----------------
Qt side of Compute (see core/compute.py): consent dialogs, the "phone is
controlling this PC" banner with a STOP button, and the pairing dialog.
The network thread asks questions through ask_pair/ask_session, which block
until you answer in the dialog (30 s without an answer counts as "No").
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from core import compute, devices

_controller: "ComputeController | None" = None


def controller() -> "ComputeController":
    global _controller
    if _controller is None:
        _controller = ComputeController()
    return _controller


class _Banner(QWidget):
    stop_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet("background:#3a0d0d; color:#ffd6d6; border:1px solid #ff5a5a; border-radius:6px;")
        lay = QHBoxLayout(self)
        self._label = QLabel("")
        lay.addWidget(self._label)
        btn = QPushButton("STOP")
        btn.setStyleSheet("background:#ff3b3b; color:white; font-weight:bold; padding:4px 14px; border:none;")
        btn.clicked.connect(self.stop_clicked)
        lay.addWidget(btn)

    def show_for(self, name: str) -> None:
        self._label.setText(f"{name} is controlling this PC")
        self.adjustSize()
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            g = screen.availableGeometry()
            self.move(g.right() - self.width() - 16, g.bottom() - self.height() - 16)
        self.show()
        self.raise_()


class ComputeController(QObject):
    _ask = Signal(str, str)        # kind, phone name
    _state = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._answer = False
        self._event = threading.Event()
        self._banner = _Banner()
        self._banner.stop_clicked.connect(self._stop)
        self._ask.connect(self._show_ask)
        self._state.connect(self._on_state)
        self.pin_listener = None       # set by the pairing dialog to learn the result
        self.host = compute.ComputeHost(devices.connected_id, self._block_pair, self._block_session,
                                        lambda k, t: self._state.emit(k, t))

    # -- called from worker threads ------------------------------------
    def _block(self, kind: str, name: str) -> bool:
        self._event.clear()
        self._answer = False
        self._ask.emit(kind, name)
        self._event.wait(35)
        return self._answer

    def _block_pair(self, name: str) -> bool:
        return self._block("pair", name)

    def _block_session(self, name: str) -> bool:
        return self._block("session", name)

    # -- GUI thread --------------------------------------------------------
    def _show_ask(self, kind: str, name: str) -> None:
        if kind == "pair":
            text = (f"{name} wants to be able to control this computer (screen, mouse, keyboard).\n\n"
                    "Only allow this if you started pairing and it is YOUR phone. Allow?")
            title = "Pair phone"
        else:
            text = f"{name} wants to start a remote session now.\n\nAllow it to control this computer?"
            title = "Remote session"
        box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        QTimer.singleShot(30000, box.reject)
        self._answer = box.exec() == QMessageBox.Yes
        self._event.set()

    def _on_state(self, kind: str, text: str) -> None:
        if kind == "session":
            self._banner.show_for(text)
            QTimer.singleShot(compute.session_minutes() * 60 * 1000, self._expire)
        elif kind == "ended":
            self._banner.hide()
        if self.pin_listener:
            self.pin_listener(kind, text)

    def _expire(self) -> None:
        if not self.host.session_active:
            self._banner.hide()

    def _stop(self) -> None:
        self.host.end_session("Stopped on the computer.")
        self._banner.hide()

    def set_ask(self, fn) -> None:
        self.host.ask_fn = fn

    def start(self) -> None:
        if getattr(self, "_watch", None) is None:      # keeps the listener on the right channel (connect / pair later)
            self._watch = QTimer(self)
            self._watch.timeout.connect(self.host.ensure)
            self._watch.start(15000)
        try:
            self.host.start()
        except Exception as e:
            print(f"[EV AI] Compute start failed: {e}")


class ComputeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Phone control (Compute)")
        self.setMinimumWidth(460)
        self._c = controller()
        lay = QVBoxLayout(self)
        intro = QLabel("Let your phone or tablet control this computer. Both devices must agree: you pair once "
                       "with a PIN, and every session asks again here. A red banner with a STOP button shows "
                       "while the phone is in control.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)
        self._pin = QLabel("")
        self._pin.setAlignment(Qt.AlignCenter)
        self._pin.setStyleSheet("font-size: 34px; letter-spacing: 8px; font-weight: bold;")
        lay.addWidget(self._pin)
        row = QHBoxLayout()
        self._pair_btn = QPushButton("Pair a phone (show PIN)")
        self._pair_btn.clicked.connect(self._pair)
        self._unpair_btn = QPushButton("Unpair")
        self._unpair_btn.clicked.connect(self._unpair)
        self._end_btn = QPushButton("END SESSION NOW")
        self._end_btn.clicked.connect(self._end_now)
        row.addWidget(self._pair_btn)
        row.addWidget(self._unpair_btn)
        row.addWidget(self._end_btn)
        lay.addLayout(row)

        # what the phone may do (turn any of these off and the phone is told "turned off on the computer")
        lay.addWidget(QLabel("WHAT THE PHONE MAY DO"))
        allowed = compute.scopes()
        self._scope_boxes = {}
        for key, label in compute.SCOPES.items():
            cb = QCheckBox(label)
            cb.setChecked(allowed[key])
            cb.toggled.connect(lambda on, k=key: compute.set_scope(k, on))
            self._scope_boxes[key] = cb
            lay.addWidget(cb)
        mins = QHBoxLayout()
        mins.addWidget(QLabel("One session lasts"))
        self._minutes = QComboBox()
        for m in compute.SESSION_CHOICES:
            self._minutes.addItem(f"{m} minutes", m)
        self._minutes.setCurrentIndex(max(0, self._minutes.findData(compute.session_minutes())))
        self._minutes.currentIndexChanged.connect(self._set_minutes)
        mins.addWidget(self._minutes)
        mins.addStretch(1)
        lay.addLayout(mins)

        lay.addWidget(QLabel("WHAT THE PHONE DID (typed text is never written down)"))
        self._log = QListWidget()
        self._log.setMinimumHeight(110)
        for t, what in self._c.host.activity[-40:]:
            self._log.addItem(f"{t}  {what}")
        self._log.scrollToBottom()
        lay.addWidget(self._log)

        self._c.pin_listener = self._on_state
        self._c.host.ensure()
        self._refresh()

    def done(self, r) -> None:
        self._c.pin_listener = None
        super().done(r)

    def _refresh(self) -> None:
        paired = self._c.host.is_paired()
        name = compute.load_store().get("name", "a phone")
        if not devices.connected_id():
            self._status.setText("First connect your phone: Settings, Connected device.")
        else:
            self._status.setText(f"Paired with {name}." if paired else "Not paired yet.")
        self._pair_btn.setEnabled(bool(devices.connected_id()))
        self._unpair_btn.setEnabled(paired)
        self._end_btn.setEnabled(self._c.host.session_active)

    def _pair(self) -> None:
        try:
            pin = self._c.host.start_pairing()
        except Exception as e:
            QMessageBox.warning(self, "Compute", str(e))
            return
        self._pin.setText(pin)
        self._status.setText("On your phone: EV AI, Computer, Compute. Type this PIN and tap Request control. "
                             "It works for 5 minutes.")

    def _unpair(self) -> None:
        self._c.host.unpair()
        self._pin.clear()
        self._refresh()

    def _set_minutes(self, _=0) -> None:
        from core import user_prefs
        v = self._minutes.currentData()
        if v:
            user_prefs.set_value("compute_minutes", int(v))

    def _end_now(self) -> None:
        self._c._stop()
        self._refresh()

    def _on_state(self, kind: str, text: str) -> None:
        if kind == "paired":
            self._pin.clear()
            self._status.setText(f"Paired with {text}.")
            self._refresh()
        elif kind == "activity":
            self._log.addItem(text)
            self._log.scrollToBottom()
        elif kind in ("session", "ended"):
            self._refresh()
