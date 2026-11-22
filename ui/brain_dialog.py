"""
ui/brain_dialog.py
--------------------
EV BRAIN: four small panels in one window.
  TRUST      how much EV may do without asking (careful / balanced / trusting)
  THOUGHTS   a live stream of what EV is doing and why
  REPLAY     do the last run of actions again
  SHORTCUTS  things you keep repeating, offered as one-word shortcuts
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QPushButton, QRadioButton,
                               QTabWidget, QVBoxLayout, QWidget)

from core import habits, replay, thoughts, trust, user_prefs
from ui.theme import dialog_stylesheet

_ICON = {"tool": "▶", "done": "✔", "fail": "✖", "ask": "❓", "note": "•"}
_LEVEL_TEXT = {
    "careful": "Careful: asks before anything that changes something (files, clipboard, saved routines, typing for you).",
    "balanced": "Balanced: asks before risky actions (typing or pressing keys for you, clicking in the browser, moving files).",
    "trusting": "Trusting: only actions that always ask (sending messages, deleting, closing apps) ask first.",
}


class BrainDialog(QDialog):
    replay_line = Signal(str)

    def __init__(self, router, parent=None):
        super().__init__(parent)
        self._router = router
        self.setWindowTitle("EV BRAIN")
        self.setMinimumSize(560, 460)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        tabs.addTab(self._trust_tab(), "TRUST")
        tabs.addTab(self._thoughts_tab(), "THOUGHTS")
        tabs.addTab(self._replay_tab(), "REPLAY")
        tabs.addTab(self._shortcut_tab(), "SHORTCUTS")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_thoughts)
        self._timer.start(700)
        self.replay_line.connect(self._on_replay_line)

    # ---- trust ----
    def _trust_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("How much may EV do without asking you first?"))
        self._radios = {}
        for key in trust.LEVELS:
            rb = QRadioButton(_LEVEL_TEXT[key])
            rb.setChecked(trust.level() == key)
            rb.toggled.connect(lambda on, k=key: on and self._set_trust(k))
            lay.addWidget(rb)
            self._radios[key] = rb
        self._asks = QLabel("")
        self._asks.setWordWrap(True)
        lay.addWidget(self._asks)
        lay.addWidget(QLabel("Before it does one of these, EV tells you in plain words what it is about to do.\n"
                             "Sending a message, deleting a file and closing an app always ask."))
        lay.addStretch(1)
        self._set_trust(trust.level())
        return w

    def _set_trust(self, key: str) -> None:
        trust.set_level(key)
        names = trust.asks_first()
        self._asks.setText("Asks first right now: " + (", ".join(n.replace("_", " ") for n in names) if names else "nothing extra"))

    # ---- thought stream ----
    def _thoughts_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("What EV is doing, live. This stays on your computer and is gone when EV closes."))
        self._stream = QListWidget()
        lay.addWidget(self._stream)
        clear = QPushButton("CLEAR")
        clear.clicked.connect(lambda: (thoughts.clear(), self._refresh_thoughts()))
        lay.addWidget(clear)
        self._last_n = -1
        self._refresh_thoughts()
        return w

    def _refresh_thoughts(self) -> None:
        items = thoughts.recent(100)
        sig = (len(items), items[-1]["t"] if items else 0)
        if sig == self._last_n:
            return
        self._last_n = sig
        self._stream.clear()
        for it in items:
            self._stream.addItem(f"{time.strftime('%H:%M:%S', time.localtime(it['t']))}  {_ICON.get(it['kind'], '•')}  {it['text']}")
        self._stream.scrollToBottom()

    # ---- replay ----
    def _replay_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Pick a run and EV does it again. Sends and deletes are skipped; anything that asks still asks."))
        self._runs = QListWidget()
        lay.addWidget(self._runs)
        row = QHBoxLayout()
        go = QPushButton("REPLAY")
        go.clicked.connect(self._do_replay)
        ref = QPushButton("REFRESH")
        ref.clicked.connect(self._load_runs)
        row.addWidget(go)
        row.addWidget(ref)
        lay.addLayout(row)
        self._report = QLabel("")
        self._report.setWordWrap(True)
        lay.addWidget(self._report)
        self._load_runs()
        return w

    def _load_runs(self) -> None:
        self._run_data = replay.runs()
        self._runs.clear()
        for r in self._run_data:
            self._runs.addItem(replay.label(r))
        if not self._run_data:
            self._runs.addItem("Nothing yet. Ask EV to do something and it shows up here.")

    def _do_replay(self) -> None:
        i = self._runs.currentRow()
        if i < 0 or i >= len(self._run_data):
            self._report.setText("Pick a run first.")
            return
        self._report.setText("Replaying…")
        run = self._run_data[i]
        threading.Thread(target=lambda: self._finish_replay(run), daemon=True).start()

    def _finish_replay(self, run) -> None:
        lines = replay.replay(self._router, run, progress=None)
        self.replay_line.emit("\n".join(lines))

    def _on_replay_line(self, text: str) -> None:
        self._report.setText(text)
        self._load_runs()

    # ---- shortcuts ----
    def _shortcut_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Things you keep doing. Save one and just say or type its name to run it."))
        self._sugs = QListWidget()
        lay.addWidget(self._sugs)
        row = QHBoxLayout()
        save = QPushButton("SAVE AS SHORTCUT")
        save.clicked.connect(self._save_shortcut)
        skip = QPushButton("NOT INTERESTED")
        skip.clicked.connect(self._skip_shortcut)
        row.addWidget(save)
        row.addWidget(skip)
        lay.addLayout(row)
        self._sug_note = QLabel("")
        self._sug_note.setWordWrap(True)
        lay.addWidget(self._sug_note)
        self._load_sugs()
        return w

    def _load_sugs(self) -> None:
        self._sug_data = habits.suggestions()
        self._sugs.clear()
        for s in self._sug_data:
            self._sugs.addItem(f"{s['name']}   ({len(s['steps'])} step{'s' if len(s['steps']) > 1 else ''}, done {s['n']} times)")
        if not self._sug_data:
            self._sugs.addItem("Nothing to suggest yet. Keep using EV and ideas show up here.")

    def _save_shortcut(self) -> None:
        i = self._sugs.currentRow()
        if i < 0 or i >= len(self._sug_data):
            self._sug_note.setText("Pick one first.")
            return
        s = self._sug_data[i]
        name, ok = QInputDialog.getText(self, "Name the shortcut", "Say or type this to run it:", text=s["name"])
        if not ok or not name.strip():
            return
        r = habits.accept(self._router, s["id"], name.strip())
        self._sug_note.setText(f"Saved. Say \"run {name.strip()}\"." if isinstance(r, dict) and r.get("status") == "saved"
                               else f"Could not save: {r.get('error') if isinstance(r, dict) else r}")
        self._load_sugs()

    def _skip_shortcut(self) -> None:
        i = self._sugs.currentRow()
        if 0 <= i < len(self._sug_data):
            habits.dismiss(self._sug_data[i]["id"])
            self._load_sugs()

    def closeEvent(self, e) -> None:
        self._timer.stop()
        super().closeEvent(e)
