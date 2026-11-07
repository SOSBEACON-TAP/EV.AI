"""
ui/game_panel.py
----------------
GAME MODE panel (left column while Game mode is on): auto-clicker with a global F6 start/stop key, performance boost,
a list of background apps you can close, and break reminders. See core/gamemode.py for the honest limits.
"""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QAbstractNativeEventFilter, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from core import gamemode, gamestats, user_prefs
from ui.widgets import HoverButton

_HOTKEY_ID, _VK_F6, _WM_HOTKEY, _NOREPEAT = 0x4746, 0x75, 0x0312, 0x4000


class _F6(QAbstractNativeEventFilter):
    """F6 starts/stops the clicker from inside any game or app (Win32 RegisterHotKey, no extra packages)."""

    def __init__(self, callback):
        super().__init__()
        self._cb, self._on = callback, False

    def enable(self) -> bool:
        if sys.platform != "win32" or self._on:
            return self._on
        try:
            import ctypes
            if ctypes.windll.user32.RegisterHotKey(None, _HOTKEY_ID, _NOREPEAT, _VK_F6):
                QApplication.instance().installNativeEventFilter(self)
                self._on = True
        except Exception:
            pass
        return self._on

    def disable(self) -> None:
        if self._on:
            try:
                import ctypes
                ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
                QApplication.instance().removeNativeEventFilter(self)
            except Exception:
                pass
            self._on = False

    def nativeEventFilter(self, event_type, message):
        if self._on and bytes(event_type) == b"windows_generic_MSG":
            try:
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    self._cb()
                    return True, 0
            except Exception:
                pass
        return False, 0


class GamePanel(QWidget):
    say = Signal(str)          # something for EV to say aloud (break reminders)
    toggle_requested = Signal()  # F6 pressed (handled on the GUI thread)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clicker = gamemode.Clicker()
        self._prev_plan: str | None = None
        self._boosted = False
        self._breaks = 0
        self._started = time.monotonic()
        self._last_break = time.monotonic()
        self._f6 = _F6(self.toggle_requested.emit)
        self.toggle_requested.connect(self._toggle_clicker)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("GAME MODE")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        self.session = QLabel("Session 00:00")
        lay.addWidget(self.session)

        def head(text):
            lab = QLabel(text)
            lab.setObjectName("SectionTitle")
            lab.setStyleSheet("margin-top: 6px;")
            lay.addWidget(lab)

        head("AUTO-CLICKER")
        row = QHBoxLayout()
        self.target = QComboBox()
        self.target.addItems(["Left mouse button", "Right mouse button"] + [f"Key: {k}" for k in gamemode.key_names()])
        row.addWidget(self.target, 3)
        self.cps = QSpinBox()
        self.cps.setRange(1, gamemode.MAX_CPS)
        self.cps.setValue(10)
        self.cps.setSuffix(" /sec")
        row.addWidget(self.cps, 2)
        lay.addLayout(row)
        self.click_btn = HoverButton("START CLICKER  (F6)")
        self.click_btn.clicked.connect(self._toggle_clicker)
        lay.addWidget(self.click_btn)
        self.click_lbl = QLabel("Off. F6 starts and stops it from any app. Mouse to the top-left corner also stops it.")
        self.click_lbl.setWordWrap(True)
        self.click_lbl.setStyleSheet("font-size: 10px; opacity: 0.8;")
        lay.addWidget(self.click_lbl)

        head("PERFORMANCE")
        row2 = QHBoxLayout()
        self.boost_btn = HoverButton("BOOST PC")
        self.boost_btn.clicked.connect(self._boost)
        self.restore_btn = HoverButton("RESTORE")
        self.restore_btn.clicked.connect(self._restore)
        row2.addWidget(self.boost_btn)
        row2.addWidget(self.restore_btn)
        lay.addLayout(row2)
        apps_btn = HoverButton("CLOSE BACKGROUND APPS")
        apps_btn.clicked.connect(self._close_apps)
        lay.addWidget(apps_btn)

        head("PROFILES")
        prow = QHBoxLayout()
        self.profile = QComboBox()
        self.profile.addItem("(choose a saved profile)")
        self.profile.addItems(sorted(gamestats.profiles()))
        self.profile.activated.connect(self._load_profile)
        prow.addWidget(self.profile, 3)
        save_p = HoverButton("SAVE")
        save_p.clicked.connect(self._save_profile)
        del_p = HoverButton("DELETE")
        del_p.clicked.connect(self._delete_profile)
        prow.addWidget(save_p, 1)
        prow.addWidget(del_p, 1)
        lay.addLayout(prow)
        stats_btn = HoverButton("MY GAME STATS")
        stats_btn.clicked.connect(self._show_stats)
        lay.addWidget(stats_btn)

        head("BREAKS")
        row3 = QHBoxLayout()
        self.break_on = QCheckBox("Remind me every")
        self.break_on.setChecked(True)
        self.break_min = QSpinBox()
        self.break_min.setRange(10, 180)
        self.break_min.setValue(45)
        self.break_min.setSuffix(" min")
        row3.addWidget(self.break_on)
        row3.addWidget(self.break_min)
        lay.addLayout(row3)
        lay.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ---------------------------------------------------------------- life cycle
    def activate(self):
        self._started = self._last_break = time.monotonic()
        self._breaks = 0
        self._timer.start(1000)
        self._f6.enable()

    def deactivate(self):
        if self._timer.isActive():
            gamestats.record_session(int(time.monotonic() - self._started), self._clicker.count, self._breaks)
        self._timer.stop()
        self._f6.disable()
        self._clicker.stop()
        self._update_click_ui()
        if self._boosted:
            self._restore()

    # ------------------------------------------------------------------- clicker
    def _target_name(self) -> str:
        t = self.target.currentText()
        return "left" if t.startswith("Left") else "right" if t.startswith("Right") else t.split(": ", 1)[1]

    def _toggle_clicker(self):
        if self._clicker.running:
            self._clicker.stop()
            self._update_click_ui()
            return
        if not user_prefs.get("game_warned"):
            QMessageBox.information(self, "Before you use the auto-clicker",
                                    "Many online games (anything with anti-cheat) treat auto-clickers as cheating and can ban "
                                    "your account. Use it in single-player games, idle/clicker games and tools.\n\n"
                                    "F6 starts and stops it. Moving the mouse to the top-left corner of the screen also stops it.")
            user_prefs.set_value("game_warned", True)
        if not self._clicker.start(self.cps.value(), self._target_name()):
            self.click_lbl.setText(self._clicker.stopped_reason or "Couldn't start.")
            return
        self._update_click_ui()

    def _update_click_ui(self):
        if self._clicker.running:
            self.click_btn.setText("STOP CLICKER  (F6)")
            self.click_lbl.setText(f"Clicking {self.cps.value()} per second: {self.target.currentText()}")
        else:
            self.click_btn.setText("START CLICKER  (F6)")
            self.click_lbl.setText(self._clicker.stopped_reason or "Off. F6 starts and stops it from any app.")

    # ------------------------------------------------------------------ boost etc.
    def _boost(self):
        ok, prev, msg = gamemode.boost()
        if ok and prev:
            self._prev_plan, self._boosted = prev, True
        self.say.emit(msg)

    def _restore(self):
        if self._boosted:
            self.say.emit(gamemode.restore(self._prev_plan))
            self._boosted = False

    def _close_apps(self):
        apps = gamemode.top_apps(10)
        if not apps:
            QMessageBox.information(self, "Background apps", "Couldn't read the list of running apps.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Close background apps")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("These use the most memory. Tick the ones you don't need while gaming.\n"
                           "Unsaved work in them is lost. Windows itself and EV AI are not listed."))
        lst = QListWidget()
        for a in apps:
            it = QListWidgetItem(f"{a['name']}   {a['mb']} MB   ({len(a['pids'])} process{'es' if len(a['pids']) != 1 else ''})")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            it.setData(Qt.UserRole, a["name"])
            lst.addItem(it)
        v.addWidget(lst)
        go = QPushButton("Close selected")
        go.clicked.connect(dlg.accept)
        v.addWidget(go)
        if dlg.exec():
            names = [lst.item(i).data(Qt.UserRole) for i in range(lst.count()) if lst.item(i).checkState() == Qt.Checked]
            if names:
                self.say.emit(f"Closed {gamemode.close_apps(names)} background processes.")

    # ------------------------------------------------------------------ profiles + stats
    def _save_profile(self):
        from PySide6.QtWidgets import QInputDialog
        current = self.profile.currentText() if self.profile.currentIndex() > 0 else ""
        name, ok = QInputDialog.getText(self, "Save profile", "Game or profile name:", text=current)
        if not ok or not name.strip():
            return
        if not gamestats.save_profile(name, self.target.currentText(), self.cps.value(), self.break_on.isChecked(), self.break_min.value()):
            QMessageBox.warning(self, "Profiles", "Couldn't save (empty name, or 30 profiles already).")
            return
        name = " ".join(name.split())[:30]
        if self.profile.findText(name) < 0:
            self.profile.addItem(name)
        self.profile.setCurrentIndex(self.profile.findText(name))
        self.say.emit(f"Saved profile {name}.")

    def _load_profile(self, index: int):
        if index <= 0:
            return
        name = self.profile.itemText(index)
        p = gamestats.profiles().get(name)
        if not p:
            return
        i = self.target.findText(p["target"])
        if i >= 0:
            self.target.setCurrentIndex(i)
        self.cps.setValue(p["cps"])
        self.break_on.setChecked(p["break_on"])
        self.break_min.setValue(p["break_min"])
        self.say.emit(f"Profile {name} loaded.")

    def _delete_profile(self):
        if self.profile.currentIndex() <= 0:
            return
        name = self.profile.currentText()
        gamestats.delete_profile(name)
        self.profile.removeItem(self.profile.currentIndex())
        self.say.emit(f"Profile {name} deleted.")

    def _show_stats(self):
        QMessageBox.information(self, "Game stats", gamestats.summary())

    def _tick(self):
        s = int(time.monotonic() - self._started)
        self.session.setText(f"Session {s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}" +
                             (f"   clicks {self._clicker.count}" if self._clicker.count else ""))
        if self._clicker.running or self._clicker.stopped_reason:
            self._update_click_ui()
        if self.break_on.isChecked() and time.monotonic() - self._last_break >= self.break_min.value() * 60:
            self._last_break = time.monotonic()
            self._breaks += 1
            self.say.emit("You have been gaming for a while, sir. Time to stretch and drink some water.")
