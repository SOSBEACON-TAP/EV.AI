"""
ui/settings_dialog.py
-----------------------
The gear-icon dialog in the top-right of the dashboard (replaced the old
static "SYSTEM ONLINE" label — that was just decoration; this is actually
useful). Groups together the handful of things that used to need a
terminal and a script: build/AI-provider info, the face-check status and
its password fallback, Windows autostart install/uninstall, and a live
view of everything EV.AI has logged since it started (see
core/log_buffer.py) — useful since the autostart launch path has no
console window to read errors from at all.

Nothing here is destructive without feedback — the autostart and
password actions all report back what happened in a message box, same
as running the underlying scripts/*.py directly would print to a
terminal.
"""

import contextlib
import io
import json
import platform
import sys

from PySide6.QtCore import QThread, Qt, QTimer, Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QInputDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider, QTextEdit, QVBoxLayout,
    QWidget, QFileDialog, QProgressBar,
)

from config import settings, APP_ROOT
from core import devices, diagnostics, profiles, updates, user_prefs
from core.log_buffer import LOG
from core.pycache_cleaner import clear_pycache
from ui.accounts_dialog import AccountsDialog, _TaskWorker
from ui.widgets import set_hover_sound_enabled
from app_version import BUILD as _BUILD
from ui.gesture_guide import GUIDE_HTML, GestureGuide
from core.personality import PERSONALITIES
from core import voices as voice_cfg
from ui.theme import THEME_CHOICES, apply_theme, dialog_stylesheet

_CHANGELOG_PATH = APP_ROOT / "CHANGELOG.md"


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "section")
    return label


def _note_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("role", "sub")
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("background: rgba(128,150,180,60); max-height: 1px; border: none;")
    return line


class _FaceEnrollWorker(QThread):
    """Runs core.face_auth.enroll_owner off the UI thread."""
    progress = Signal(int, int)
    finished_with = Signal(dict)

    def run(self) -> None:
        try:
            from core.face_auth import enroll_owner
            result = enroll_owner(progress_callback=lambda cur, total: self.progress.emit(cur, total))
        except Exception as e:  # never let a camera problem crash the app
            result = {"error": str(e)}
        self.finished_with.emit(result)


class SettingsDialog(QDialog):
    always_on_top_changed = Signal(bool)
    minimize_to_tray_changed = Signal(bool)
    global_hotkey_changed = Signal(bool)
    profile_applied = Signal(str)
    replay_intro_requested = Signal()
    quick_actions_requested = Signal()
    focus_toggle_requested = Signal()
    ask_ai_requested = Signal(str)
    look_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{settings.APP_NAME} — Settings")
        self.setFixedWidth(440)
        self.setMaximumHeight(640)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 16)
        outer.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search settings — try “voice”, “API”, “theme”…")
        self._search.setClearButtonEnabled(True)
        self._search.setContentsMargins(20, 0, 20, 0)
        self._search.textChanged.connect(self._apply_search)
        search_row = QHBoxLayout()
        search_row.setContentsMargins(20, 14, 20, 0)
        search_row.addWidget(self._search)
        outer.addLayout(search_row)

        # Everything scrolls, so the dialog stays a sane height now that
        # there are this many sections.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        root = QVBoxLayout(body)
        root.setContentsMargins(20, 18, 20, 8)
        root.setSpacing(10)

        header = QLabel(f"{settings.APP_NAME} {settings.APP_VERSION} (build {_BUILD})")
        header.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(header)

        provider = (settings.AI_PROVIDER or "—").title()
        info = QLabel(
            f"Platform: {platform.system()} {platform.release()}\n"
            f"AI provider: {provider}\nModel: {settings.AI_MODEL or '—'}"
        )
        info.setProperty("role", "sub")
        root.addWidget(info)

        root.addWidget(_divider())

        # -- Profiles -------------------------------------------------------
        root.addWidget(_section_title("PROFILE"))
        profile_row = QHBoxLayout()
        self._profile_combo = QComboBox()
        for name in profiles.PROFILES:
            self._profile_combo.addItem(name)
        current_profile = user_prefs.get("profile")
        self._profile_combo.setCurrentIndex(max(self._profile_combo.findText(current_profile), 0))
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        apply_profile_btn = QPushButton("Apply")
        apply_profile_btn.clicked.connect(self._on_apply_profile)
        profile_row.addWidget(self._profile_combo, 1)
        profile_row.addWidget(apply_profile_btn)
        root.addLayout(profile_row)
        self._profile_note = _note_label(profiles.PROFILES[self._profile_combo.currentText()]["about"])
        root.addWidget(self._profile_note)

        root.addWidget(_divider())

        # -- AI / email / voice accounts -----------------------------------
        root.addWidget(_section_title("AI, EMAIL & VOICE"))
        accounts_label = QLabel("Change the AI provider and API key, the email (Outlook) account, and voice options.")
        accounts_label.setWordWrap(True)
        root.addWidget(accounts_label)
        accounts_btn = QPushButton("Open account settings…")
        accounts_btn.clicked.connect(lambda: AccountsDialog(self).exec())
        root.addWidget(accounts_btn)

        root.addWidget(_divider())

        # -- Appearance ----------------------------------------------------
        root.addWidget(_section_title("APPEARANCE"))
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme"))
        theme_row.addStretch(1)
        self._theme_combo = QComboBox()
        for _tid, _label in THEME_CHOICES:
            self._theme_combo.addItem(_label, _tid)
        self._theme_combo.setCurrentIndex(max(self._theme_combo.findData(user_prefs.get("theme")), 0))
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self._theme_combo)
        root.addLayout(theme_row)
        theme_note = QLabel("The HUD overlay and startup screen stay dark in every theme.")
        theme_note.setWordWrap(True)
        theme_note.setProperty("role", "sub")
        root.addWidget(theme_note)

        # Live preview: picking a theme applies it right away so you can see
        # it; it only sticks once you press Keep (closing the window undoes it).
        self._saved_theme = user_prefs.get("theme")
        self._preview_box = QWidget()
        preview_row = QHBoxLayout(self._preview_box)
        preview_row.setContentsMargins(0, 0, 0, 0)
        self._preview_label = QLabel("Previewing…")
        keep_btn = QPushButton("Keep")
        keep_btn.clicked.connect(self._keep_theme)
        undo_btn = QPushButton("Undo")
        undo_btn.clicked.connect(self._undo_theme)
        preview_row.addWidget(self._preview_label, 1)
        preview_row.addWidget(keep_btn)
        preview_row.addWidget(undo_btn)
        self._preview_box.setVisible(False)
        root.addWidget(self._preview_box)

        root.addWidget(_divider())

        # -- Personality ---------------------------------------------------
        root.addWidget(_section_title("PERSONALITY"))
        pers_row = QHBoxLayout()
        pers_row.addWidget(QLabel("How EV talks"))
        pers_row.addStretch(1)
        self._personality_combo = QComboBox()
        for key, (label, _prompt) in PERSONALITIES.items():
            self._personality_combo.addItem(label, key)
        self._personality_combo.setCurrentIndex(max(self._personality_combo.findData(user_prefs.get("personality")), 0))
        self._personality_combo.currentIndexChanged.connect(
            lambda: user_prefs.set_value("personality", self._personality_combo.currentData()))
        pers_row.addWidget(self._personality_combo)
        root.addLayout(pers_row)
        root.addWidget(_note_label("Professional = precise and formal. Friendly = warm and upbeat. "
                                   "Humorous = playful. Applies from the next reply; it never changes what EV is allowed to do."))

        self._voice_check = QCheckBox("Give each personality its own voice (natural voices, needs internet)")
        self._voice_check.setChecked(user_prefs.get("voice_per_personality"))
        self._voice_check.toggled.connect(lambda on: user_prefs.set_value("voice_per_personality", on))
        root.addWidget(self._voice_check)
        self._voice_combos = {}
        for key in ("professional", "friendly", "humorous"):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{PERSONALITIES[key][0]} voice"))
            row.addStretch(1)
            combo = QComboBox()
            for vid, label in voice_cfg.VOICE_CHOICES:
                combo.addItem(label, vid)
            pref_key = voice_cfg.STYLE[key][0]
            combo.setCurrentIndex(max(combo.findData(user_prefs.get(pref_key)), 0))
            combo.currentIndexChanged.connect(lambda _=0, c=combo, k=pref_key: user_prefs.set_value(k, c.currentData()))
            self._voice_combos[pref_key] = combo
            row.addWidget(combo)
            root.addLayout(row)
        self._voice_preview_btn = QPushButton("▶ Preview the current personality's voice")
        self._voice_preview_btn.clicked.connect(self._preview_personality_voice)
        root.addWidget(self._voice_preview_btn)
        root.addWidget(_note_label("If the natural voice can't be reached, EV uses the offline Windows voice instead. "
                                   "Default keeps the voice from account settings."))

        root.addWidget(_divider())

        # -- Personalization -------------------------------------------------
        root.addWidget(_section_title("PERSONALIZATION"))
        self._look_timer = QTimer(self)
        self._look_timer.setSingleShot(True)
        self._look_timer.timeout.connect(self._apply_look)
        self._font_slider = self._add_look_slider(root, "Text size", "font_scale", 80, 150, "%")
        self._opacity_slider = self._add_look_slider(root, "Window opacity", "window_opacity", 60, 100, "%")
        root.addWidget(_note_label("Custom theme colours (pick “Custom” in Appearance → Theme). Dark backgrounds work best."))
        self._swatches = {}
        colours_row = QHBoxLayout()
        for key, text in (("custom_accent1", "Accent 1"), ("custom_accent2", "Accent 2"), ("custom_bg", "Background")):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, k=key: self._pick_colour(k))
            self._swatches[key] = btn
            colours_row.addWidget(btn)
        root.addLayout(colours_row)
        self._refresh_swatches()
        use_custom = QPushButton("Use my custom theme")
        use_custom.clicked.connect(self._use_custom_theme)
        root.addWidget(use_custom)

        preset_row = QHBoxLayout()
        self._preset_combo = QComboBox()
        preset_row.addWidget(self._preset_combo, 1)
        apply_preset = QPushButton("Apply")
        apply_preset.clicked.connect(self._apply_preset)
        delete_preset = QPushButton("Delete")
        delete_preset.clicked.connect(self._delete_preset)
        preset_row.addWidget(apply_preset)
        preset_row.addWidget(delete_preset)
        root.addLayout(preset_row)
        save_preset = QPushButton("Save current look as a preset…")
        save_preset.clicked.connect(self._save_preset)
        root.addWidget(save_preset)
        self._refresh_presets()

        root.addWidget(_divider())

        # -- Gesture control -----------------------------------------------
        root.addWidget(_section_title("GESTURE CONTROL"))
        self._gesture_check = QCheckBox("Enable hand-gesture actions")
        self._gesture_check.setChecked(user_prefs.get("gestures_enabled"))
        self._gesture_check.toggled.connect(lambda on: user_prefs.set_value("gestures_enabled", on))
        root.addWidget(self._gesture_check)
        root.addWidget(_note_label(
            "Hold your hand(s) in front of the webcam, about an arm's length away, with good light. "
            "Changes here apply immediately, even while Video mode is running."))
        guide = QLabel(GUIDE_HTML)
        guide.setTextFormat(Qt.RichText)
        guide.setWordWrap(True)
        root.addWidget(guide)

        resume_row = QHBoxLayout()
        resume_row.addWidget(QLabel("Resume recognition with"))
        resume_row.addStretch(1)
        self._resume_combo = QComboBox()
        self._resume_combo.addItem("A held fist", "fist")
        self._resume_combo.addItem("An open palm held again", "palm")
        self._resume_combo.setCurrentIndex(max(self._resume_combo.findData(user_prefs.get("gesture_resume_mode")), 0))
        self._resume_combo.currentIndexChanged.connect(
            lambda: user_prefs.set_value("gesture_resume_mode", self._resume_combo.currentData()))
        resume_row.addWidget(self._resume_combo)
        root.addLayout(resume_row)

        self._gesture_sliders = []
        for text, key, lo, hi, scale, suffix in (
            ("Swipe distance (smaller = easier)", "gesture_swipe_distance", 10, 50, 100, "%"),
            ("Swipe cooldown", "gesture_swipe_cooldown", 3, 30, 10, " s"),
            ("Zoom sensitivity step (smaller = more sensitive)", "gesture_zoom_step", 2, 20, 100, "%"),
            ("Zoom cooldown", "gesture_zoom_cooldown", 5, 100, 100, " s"),
            ("Volume movement needed (smaller = easier)", "gesture_volume_distance", 5, 40, 100, "%"),
            ("Volume cooldown", "gesture_volume_cooldown", 10, 100, 100, " s"),
            ("Volume change per step", "gesture_volume_step", 1, 20, 1, "%"),
            ("Finger-count hold time", "gesture_hold_time", 3, 30, 10, " s"),
            ("Finger-count cooldown", "gesture_finger_cooldown", 5, 50, 10, " s"),
            ("Open-palm hold time to pause", "gesture_pause_hold", 3, 30, 10, " s"),
            ("Hold time to resume", "gesture_resume_hold", 5, 50, 10, " s"),
        ):
            self._add_gesture_slider(root, text, key, lo, hi, scale, suffix)

        show_guide = QPushButton("Show gesture guide")
        show_guide.clicked.connect(lambda: GestureGuide(self).show())
        root.addWidget(show_guide)
        reset_gestures = QPushButton("Reset gesture settings")
        reset_gestures.clicked.connect(self._on_reset_gestures)
        root.addWidget(reset_gestures)
        root.addWidget(_note_label(
            "Tip: if gestures trigger by accident, raise the cooldowns or hold times; if they are hard to trigger, "
            "lower the swipe / volume distances. For exact volume steps install: pip install pycaw comtypes"))

        root.addWidget(_divider())

        # -- Quick Actions ------------------------------------------------------
        root.addWidget(_section_title("QUICK ACTIONS"))
        root.addWidget(_note_label("Quick Actions are your own one-word commands, like “study mode”, that open "
                                   "several apps and sites at once."))
        qa_btn = QPushButton("Open Quick Actions…")
        qa_btn.clicked.connect(self.quick_actions_requested.emit)
        root.addWidget(qa_btn)

        root.addWidget(_divider())

        # -- Focus Mode ----------------------------------------------------------
        root.addWidget(_section_title("FOCUS MODE"))
        root.addWidget(_note_label("Focus Mode turns on the quiet corner mode, runs the Quick Action named below, "
                                   "and closes (or warns about) the sites and apps you block. "
                                   "Type site or app names, like: youtube, scratch, discord"))
        chain_row = QHBoxLayout()
        chain_row.addWidget(QLabel("Quick Action to run"))
        self._focus_chain = QLineEdit(user_prefs.get("focus_chain"))
        self._focus_chain.editingFinished.connect(
            lambda: user_prefs.set_value("focus_chain", self._focus_chain.text().strip().lower()))
        chain_row.addWidget(self._focus_chain, 1)
        root.addLayout(chain_row)
        root.addWidget(QLabel("Blocked sites / apps (comma separated)"))
        self._focus_blocked = QLineEdit(user_prefs.get("focus_blocked"))
        self._focus_blocked.editingFinished.connect(
            lambda: user_prefs.set_value("focus_blocked", self._focus_blocked.text().strip()))
        self._focus_blocked.textChanged.connect(
            lambda t: user_prefs.set_value("focus_blocked", t.strip()))
        root.addWidget(self._focus_blocked)
        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("When one is open"))
        action_row.addStretch(1)
        self._focus_action = QComboBox()
        self._focus_action.addItem("Close it", "close")
        self._focus_action.addItem("Only warn me", "warn")
        self._focus_action.setCurrentIndex(max(self._focus_action.findData(user_prefs.get("focus_action")), 0))
        self._focus_action.currentIndexChanged.connect(
            lambda: user_prefs.set_value("focus_action", self._focus_action.currentData()))
        action_row.addWidget(self._focus_action)
        root.addLayout(action_row)
        focus_btn = QPushButton("Start / stop Focus Mode")
        focus_btn.clicked.connect(self.focus_toggle_requested.emit)
        root.addWidget(focus_btn)

        root.addWidget(_divider())

        # -- Clipboard assistant -----------------------------------------------
        root.addWidget(_section_title("CLIPBOARD ASSISTANT"))
        root.addWidget(_note_label("Copy any text, then use these — or just say “summarize my clipboard”. "
                                   "EV only reads the clipboard when you ask."))
        clip_row = QHBoxLayout()
        sum_btn = QPushButton("Summarize clipboard")
        sum_btn.clicked.connect(lambda: self._ask_ai("Summarize the text on my clipboard in a few clear bullet points."))
        rew_btn = QPushButton("Rewrite clearly")
        rew_btn.clicked.connect(lambda: self._ask_ai(
            "Rewrite the text on my clipboard so it is clearer and more polished, keep the meaning, "
            "then put the rewritten version back on my clipboard."))
        clip_row.addWidget(sum_btn)
        clip_row.addWidget(rew_btn)
        root.addLayout(clip_row)

        root.addWidget(_divider())

        # -- Error Doctor --------------------------------------------------------
        root.addWidget(_section_title("ERROR DOCTOR"))
        root.addWidget(_note_label("Checks packages, your AI key, internet, webcam and EV's log for known problems "
                                   "and tells you how to fix each one."))
        doctor_btn = QPushButton("Run Error Doctor")
        doctor_btn.clicked.connect(self._open_error_doctor)
        root.addWidget(doctor_btn)

        root.addWidget(_divider())

        # -- App usage insights ---------------------------------------------------
        root.addWidget(_section_title("APP USAGE INSIGHTS"))
        root.addWidget(_note_label("Shows how long you spend in each app (the window in front), top apps, "
                                   "categories and a 7-day trend. Stored only on this computer — no window titles, "
                                   "no screenshots."))
        self._usage_check = QCheckBox("Track which app I'm using")
        self._usage_check.setChecked(user_prefs.get("usage_tracking"))
        self._usage_check.toggled.connect(lambda on: user_prefs.set_value("usage_tracking", on))
        root.addWidget(self._usage_check)
        insights_btn = QPushButton("Open usage insights…")
        insights_btn.clicked.connect(self._open_insights)
        root.addWidget(insights_btn)
        root.addWidget(_note_label("Ask EV: “how much time did I spend coding today?” or “which app did I use the most?”. "
                                   "Exclude apps or clear history inside the insights window."))

        root.addWidget(_divider())

        # -- File finder ------------------------------------------------------------
        root.addWidget(_section_title("FILE FINDER"))
        root.addWidget(_note_label("Find files by describing them: “my EV AI python file”, “images in Downloads”, "
                                   "“the presentation I edited recently”, “my Arduino projects”. Searches file names "
                                   "and folders only, never what's inside."))
        finder_btn = QPushButton("Open File Finder…")
        finder_btn.clicked.connect(self._open_finder)
        root.addWidget(finder_btn)
        root.addWidget(QLabel("Extra folders to search (separate with ;)"))
        self._finder_folders = QLineEdit(user_prefs.get("finder_folders"))
        self._finder_folders.setPlaceholderText(r"D:\Projects;E:\Study")
        self._finder_folders.editingFinished.connect(
            lambda: user_prefs.set_value("finder_folders", self._finder_folders.text().strip()))
        root.addWidget(self._finder_folders)
        root.addWidget(_note_label("Already included: Desktop, Documents, Downloads, Pictures, Videos, Music, OneDrive and "
                                   "the EV AI folder. Press Refresh index in the File Finder after adding folders."))

        root.addWidget(_divider())

        # -- Connected device ----------------------------------------------------
        root.addWidget(_section_title("CONNECTED DEVICE"))
        root.addWidget(_note_label("Connect your phone with its device code. If you give EV a task and the computer "
                                   "is switched off before it finishes, EV rings your phone in the app over the "
                                   "internet, like a WhatsApp call: no SIM balance or phone number needed. Keep the "
                                   "code private."))
        self._device_status = QLabel()
        root.addWidget(self._device_status)
        code_row = QHBoxLayout()
        self._device_code = QLineEdit()
        self._device_code.setPlaceholderText("Device code, e.g. EV-4K9QZ-7TW2M-X")
        self._device_connect_btn = QPushButton("Connect")
        self._device_connect_btn.clicked.connect(self._connect_device)
        self._device_disconnect_btn = QPushButton("Disconnect")
        self._device_disconnect_btn.clicked.connect(self._disconnect_device)
        code_row.addWidget(self._device_code, 1)
        code_row.addWidget(self._device_connect_btn)
        code_row.addWidget(self._device_disconnect_btn)
        root.addLayout(code_row)
        self._call_check = QCheckBox("Ring my phone if the computer shuts down while EV is working")
        self._call_check.setChecked(user_prefs.get("call_on_shutdown"))
        self._call_check.toggled.connect(lambda on: user_prefs.set_value("call_on_shutdown", on))
        root.addWidget(self._call_check)
        dev_row = QHBoxLayout()
        self._test_call_btn = QPushButton("Send a test ring")
        self._test_call_btn.clicked.connect(self._test_call)
        new_code_btn = QPushButton("Make a code for a new phone…")
        new_code_btn.clicked.connect(self._make_code)
        dev_row.addWidget(self._test_call_btn)
        dev_row.addWidget(new_code_btn)
        root.addLayout(dev_row)
        compute_btn = QPushButton("Phone control (Compute)…")
        compute_btn.clicked.connect(self._open_compute)
        root.addWidget(compute_btn)
        self._refresh_device_status()

        root.addWidget(_divider())

        # -- Behaviour -----------------------------------------------------
        root.addWidget(_section_title("BEHAVIOUR"))
        self._speak_check = QCheckBox("Speak replies aloud")
        self._speak_check.setChecked(user_prefs.get("speak_replies"))
        self._speak_check.toggled.connect(lambda on: user_prefs.set_value("speak_replies", on))
        root.addWidget(self._speak_check)

        self._top_check = QCheckBox("Keep the dashboard above other windows")
        self._top_check.setChecked(user_prefs.get("always_on_top"))
        self._top_check.toggled.connect(self._on_always_on_top)
        root.addWidget(self._top_check)

        self._tray_check = QCheckBox("Minimize to the system tray when closed")
        self._tray_check.setChecked(user_prefs.get("minimize_to_tray"))
        self._tray_check.toggled.connect(self._on_tray_toggled)
        root.addWidget(self._tray_check)

        self._start_tray_check = QCheckBox("Start hidden in the tray (needs the option above)")
        self._start_tray_check.setChecked(user_prefs.get("start_in_tray"))
        self._start_tray_check.toggled.connect(lambda on: user_prefs.set_value("start_in_tray", on))
        root.addWidget(self._start_tray_check)

        self._hotkey_check = QCheckBox("Global hotkey: Ctrl+Alt+E shows / hides EV")
        self._hotkey_check.setChecked(user_prefs.get("global_hotkey"))
        self._hotkey_check.toggled.connect(self._on_hotkey_toggled)
        root.addWidget(self._hotkey_check)

        self._hover_check = QCheckBox("Play a soft sound when hovering buttons")
        self._hover_check.setChecked(user_prefs.get("hover_sound"))
        self._hover_check.toggled.connect(self._on_hover_sound)
        root.addWidget(self._hover_check)

        self._offline_check = QCheckBox("Handle simple commands without the AI (faster, works offline)")
        self._offline_check.setChecked(user_prefs.get("offline_first"))
        self._offline_check.toggled.connect(lambda on: user_prefs.set_value("offline_first", on))
        root.addWidget(self._offline_check)

        self._confirm_send_check = QCheckBox("Ask before sending emails / WhatsApp messages")
        self._confirm_send_check.setChecked(user_prefs.get("confirm_before_sending"))
        self._confirm_send_check.toggled.connect(lambda on: user_prefs.set_value("confirm_before_sending", on))
        root.addWidget(self._confirm_send_check)

        self._briefing_check = QCheckBox("Read a morning briefing when EV opens")
        self._briefing_check.setChecked(user_prefs.get("briefing_on_start"))
        self._briefing_check.toggled.connect(lambda on: user_prefs.set_value("briefing_on_start", on))
        root.addWidget(self._briefing_check)

        obs_row = QHBoxLayout()
        obs_row.addWidget(QLabel("Observe mode checks the screen every"))
        obs_row.addStretch(1)
        self._observe_combo = QComboBox()
        for seconds in (10, 20, 30, 60, 120):
            self._observe_combo.addItem(f"{seconds}s", seconds)
        current = user_prefs.get("observe_interval_s")
        self._observe_combo.setCurrentIndex(max(self._observe_combo.findData(current), 1))
        self._observe_combo.currentIndexChanged.connect(
            lambda: user_prefs.set_value("observe_interval_s", self._observe_combo.currentData())
        )
        obs_row.addWidget(self._observe_combo)
        root.addLayout(obs_row)
        root.addWidget(_note_label("Applies the next time Observe is turned on."))

        root.addWidget(_divider())

        # -- Maintenance ----------------------------------------------------
        root.addWidget(_section_title("DATA"))
        data_row = QHBoxLayout()
        save_chat_btn = QPushButton("Save conversation…")
        save_chat_btn.clicked.connect(self._on_save_conversation)
        folder_btn = QPushButton("Open data folder")
        folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_ROOT))))
        data_row.addWidget(save_chat_btn)
        data_row.addWidget(folder_btn)
        root.addLayout(data_row)

        root.addWidget(_divider())

        # -- Face check + password fallback --------------------------------
        root.addWidget(_section_title("STARTUP FACE CHECK"))
        self._face_status = QLabel()
        self._face_status.setWordWrap(True)
        self._face_status.setProperty("role", "sub")
        root.addWidget(self._face_status)
        self._refresh_face_status()

        face_row = QHBoxLayout()
        self._face_setup_btn = QPushButton("Face recognition setup")
        self._face_setup_btn.clicked.connect(self._on_face_setup)
        face_row.addWidget(self._face_setup_btn)
        self._face_toggle_btn = QPushButton()
        self._face_toggle_btn.clicked.connect(self._on_face_toggle)
        face_row.addWidget(self._face_toggle_btn)
        root.addLayout(face_row)
        self._refresh_face_status()

        pw_row = QHBoxLayout()
        self._pw_btn = QPushButton("Set / change password fallback")
        self._pw_btn.clicked.connect(self._on_set_password)
        pw_row.addWidget(self._pw_btn)
        root.addLayout(pw_row)

        root.addWidget(_divider())

        # -- Privacy center ------------------------------------------------
        root.addWidget(_section_title("PRIVACY"))
        root.addWidget(_note_label("See what EV.AI can hear, see and reach right now, what it "
                                   "stores, and everything it has done."))
        privacy_btn = QPushButton("Open privacy center")
        privacy_btn.clicked.connect(self._on_open_privacy)
        root.addWidget(privacy_btn)

        root.addWidget(_divider())

        # -- Log ----------------------------------------------------------
        root.addWidget(_section_title("ACTIVITY LOG"))
        log_label = QLabel("Everything EV.AI has logged since it started.")
        log_label.setWordWrap(True)
        root.addWidget(log_label)
        view_log_btn = QPushButton("View log")
        view_log_btn.clicked.connect(self._on_view_log)
        root.addWidget(view_log_btn)

        root.addWidget(_divider())

        # -- System & About -------------------------------------------------
        root.addWidget(_section_title("SYSTEM & ABOUT"))
        root.addWidget(_note_label(f"{settings.APP_NAME} version {settings.APP_VERSION} (build {_BUILD})"))
        about_row = QHBoxLayout()
        self._update_btn = QPushButton("Check for updates")
        self._update_btn.clicked.connect(self._on_check_updates)
        diag_btn = QPushButton("Diagnostics & logs")
        diag_btn.clicked.connect(self._on_diagnostics)
        about_row.addWidget(self._update_btn)
        about_row.addWidget(diag_btn)
        root.addLayout(about_row)
        self._auto_update_check = QCheckBox("Tell me when an update is available (checked when EV opens)")
        self._auto_update_check.setChecked(user_prefs.get("auto_check_updates"))
        self._auto_update_check.toggled.connect(lambda on: user_prefs.set_value("auto_check_updates", on))
        root.addWidget(self._auto_update_check)
        io_row = QHBoxLayout()
        export_btn = QPushButton("Export settings…")
        export_btn.clicked.connect(self._on_export_settings)
        import_btn = QPushButton("Import settings…")
        import_btn.clicked.connect(self._on_import_settings)
        io_row.addWidget(export_btn)
        io_row.addWidget(import_btn)
        root.addLayout(io_row)
        replay_btn = QPushButton("Replay intro animation")
        replay_btn.clicked.connect(self._on_replay_intro)
        root.addWidget(replay_btn)

        reset_btn = QPushButton("Reset settings to defaults")
        reset_btn.clicked.connect(self._on_reset_settings)
        root.addWidget(reset_btn)
        root.addWidget(_note_label("Export/import and reset cover the switches on this page — "
                                   "not your API keys, email or password."))

        root.addWidget(_divider())

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        outer.addWidget(close_btn)
        outer.setAlignment(close_btn, Qt.AlignHCenter)

        self._root_layout = root
        self._search_groups = self._index_groups(root)

    # -- preference handlers ------------------------------------------------
    def _on_theme_changed(self) -> None:
        theme = self._theme_combo.currentData()
        if theme == self._saved_theme:
            self._preview_box.setVisible(False)
        else:
            self._preview_label.setText(f"Previewing {self._theme_combo.currentText().lower()}")
            self._preview_box.setVisible(True)
        apply_theme(QApplication.instance(), theme)
        self.setStyleSheet(dialog_stylesheet(theme))

    def _keep_theme(self) -> None:
        self._saved_theme = self._theme_combo.currentData()
        user_prefs.set_value("theme", self._saved_theme)
        self._preview_box.setVisible(False)

    def _undo_theme(self) -> None:
        index = self._theme_combo.findData(self._saved_theme)
        self._theme_combo.blockSignals(True)
        self._theme_combo.setCurrentIndex(max(index, 0))
        self._theme_combo.blockSignals(False)
        apply_theme(QApplication.instance(), self._saved_theme)
        self.setStyleSheet(dialog_stylesheet(self._saved_theme))
        self._preview_box.setVisible(False)

    def done(self, result) -> None:
        # An un-kept theme preview is undone when the window closes.
        if self._preview_box.isVisible():
            apply_theme(QApplication.instance(), self._saved_theme)
        super().done(result)

    def _on_hover_sound(self, enabled: bool) -> None:
        user_prefs.set_value("hover_sound", enabled)
        set_hover_sound_enabled(enabled)

    # -- profiles --------------------------------------------------------------
    def _on_profile_selected(self) -> None:
        self._profile_note.setText(profiles.PROFILES[self._profile_combo.currentText()]["about"])

    def _on_apply_profile(self) -> None:
        name = self._profile_combo.currentText()
        for key, value in profiles.PROFILES[name]["prefs"].items():
            user_prefs.set_value(key, value)
        user_prefs.set_value("profile", name)
        self._apply_prefs_live()
        self.profile_applied.emit(name)

    def _apply_prefs_live(self) -> None:
        """After prefs were changed in bulk (profile / import / reset): refresh
        every control on this page and push the changes to the running app."""
        checks = {
            self._speak_check: "speak_replies", self._top_check: "always_on_top",
            self._tray_check: "minimize_to_tray", self._start_tray_check: "start_in_tray",
            self._hotkey_check: "global_hotkey", self._hover_check: "hover_sound",
            self._offline_check: "offline_first", self._briefing_check: "briefing_on_start",
            self._auto_update_check: "auto_check_updates",
            self._confirm_send_check: "confirm_before_sending",
        }
        for box, key in checks.items():
            box.blockSignals(True)
            box.setChecked(user_prefs.get(key))
            box.blockSignals(False)
        self._observe_combo.blockSignals(True)
        self._observe_combo.setCurrentIndex(max(self._observe_combo.findData(user_prefs.get("observe_interval_s")), 1))
        self._observe_combo.blockSignals(False)

        prefs_now = user_prefs.load()
        self._gesture_check.blockSignals(True)
        self._gesture_check.setChecked(prefs_now["gestures_enabled"])
        self._gesture_check.blockSignals(False)
        self._resume_combo.blockSignals(True)
        self._resume_combo.setCurrentIndex(max(self._resume_combo.findData(prefs_now["gesture_resume_mode"]), 0))
        self._resume_combo.blockSignals(False)
        for key, slider, scale in self._gesture_sliders:
            slider.blockSignals(True)
            slider.setValue(int(round(prefs_now[key] * scale)) if scale != 1 else int(prefs_now[key]))
            slider.blockSignals(False)

        for combo, key in ((self._personality_combo, "personality"), (self._focus_action, "focus_action")):
            combo.blockSignals(True)
            combo.setCurrentIndex(max(combo.findData(prefs_now[key]), 0))
            combo.blockSignals(False)
        self._voice_check.blockSignals(True)
        self._voice_check.setChecked(prefs_now["voice_per_personality"])
        self._voice_check.blockSignals(False)
        for pref_key, combo in self._voice_combos.items():
            combo.blockSignals(True)
            combo.setCurrentIndex(max(combo.findData(prefs_now[pref_key]), 0))
            combo.blockSignals(False)
        self._usage_check.blockSignals(True)
        self._usage_check.setChecked(prefs_now["usage_tracking"])
        self._usage_check.blockSignals(False)
        self._finder_folders.setText(prefs_now["finder_folders"])
        self._focus_chain.setText(prefs_now["focus_chain"])
        self._focus_blocked.setText(prefs_now["focus_blocked"])
        for slider, key in ((self._font_slider, "font_scale"), (self._opacity_slider, "window_opacity")):
            slider.blockSignals(True)
            slider.setValue(int(prefs_now[key]))
            slider.blockSignals(False)
            slider._value_label.setText(f"{slider.value()}{slider._suffix}")
        self._refresh_swatches()
        self._refresh_presets()

        theme = user_prefs.get("theme")
        self._saved_theme = theme
        self._preview_box.setVisible(False)
        self._theme_combo.blockSignals(True)
        self._theme_combo.setCurrentIndex(max(self._theme_combo.findData(theme), 0))
        self._theme_combo.blockSignals(False)
        apply_theme(QApplication.instance(), theme)
        self.setStyleSheet(dialog_stylesheet(theme))

        set_hover_sound_enabled(user_prefs.get("hover_sound"))
        sys.dont_write_bytecode = user_prefs.get("auto_clear_pycache")
        index = self._profile_combo.findText(user_prefs.get("profile"))
        self._profile_combo.blockSignals(True)
        self._profile_combo.setCurrentIndex(max(index, 0))
        self._profile_combo.blockSignals(False)
        self._on_profile_selected()
        self.always_on_top_changed.emit(user_prefs.get("always_on_top"))
        self.minimize_to_tray_changed.emit(user_prefs.get("minimize_to_tray"))
        self.global_hotkey_changed.emit(user_prefs.get("global_hotkey"))

    # -- system & about ---------------------------------------------------------
    def _on_check_updates(self) -> None:
        from ui.update_flow import UpdateFlow
        self._update_flow = UpdateFlow(self, self._update_btn)
        self._update_flow.start()

    def _on_diagnostics(self) -> None:
        report = diagnostics.build_report()
        box = QDialog(self)
        box.setWindowTitle(f"{settings.APP_NAME} — Diagnostics")
        box.setStyleSheet(self.styleSheet())
        box.resize(640, 480)
        layout = QVBoxLayout(box)
        layout.addWidget(_note_label("Safe to share: API keys and passwords are never included."))
        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Consolas", 9))
        text.setPlainText(report)
        layout.addWidget(text)
        row = QHBoxLayout()
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(report))
        save_btn = QPushButton("Save to file…")

        def _save() -> None:
            path, _ = QFileDialog.getSaveFileName(box, "Save diagnostics", "ev_ai_diagnostics.txt", "Text files (*.txt)")
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(report)
                except OSError as e:
                    QMessageBox.warning(box, "Diagnostics", f"Couldn't save: {e}")

        save_btn.clicked.connect(_save)
        log_btn = QPushButton("Full log")
        log_btn.clicked.connect(self._on_view_log)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(box.accept)
        for b in (copy_btn, save_btn, log_btn, close_btn):
            row.addWidget(b)
        layout.addLayout(row)
        box.exec()

    def _on_export_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export settings", "ev_ai_settings.json", "JSON (*.json)")
        if not path:
            return
        payload = {"app": settings.APP_NAME, "version": settings.APP_VERSION, "settings": user_prefs.load()}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except OSError as e:
            QMessageBox.warning(self, "Export settings", f"Couldn't save: {e}")
            return
        QMessageBox.information(self, "Export settings", "Settings exported.")

    def _on_import_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import settings", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            incoming = data.get("settings") if isinstance(data, dict) else None
            if not isinstance(incoming, dict):
                raise ValueError("not an EV.AI settings file")
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import settings", f"That file couldn't be read as settings: {e}")
            return
        applied = 0
        for key, default in user_prefs.DEFAULTS.items():
            if key in incoming and type(incoming[key]) is type(default):
                user_prefs.set_value(key, incoming[key])
                applied += 1
        self._apply_prefs_live()
        QMessageBox.information(self, "Import settings", f"Imported {applied} setting{'s' if applied != 1 else ''}.")

    def _add_gesture_slider(self, root, text, key, lo, hi, scale, suffix) -> None:
        """One labelled slider bound to a saved gesture_* setting."""
        is_int = isinstance(user_prefs.DEFAULTS[key], int)
        row = QHBoxLayout()
        label = QLabel(text)
        label.setWordWrap(True)
        value_label = QLabel()
        value_label.setMinimumWidth(52)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setMinimumWidth(110)
        current = user_prefs.get(key)
        slider.setValue(int(round(current * scale)) if scale != 1 else int(current))

        def show(v):
            shown = v if scale == 1 else v / scale * (100 if suffix == "%" else 1)
            value_label.setText(f"{shown:g}{suffix}" if scale == 1 else
                                (f"{shown:.0f}{suffix}" if suffix == "%" else f"{shown:.1f}{suffix}" if scale == 10 else f"{shown:.2f}{suffix}"))

        def save(v):
            show(v)
            user_prefs.set_value(key, int(v) if is_int else v / scale)

        slider.valueChanged.connect(save)
        show(slider.value())
        row.addWidget(label, 1)
        row.addWidget(slider)
        row.addWidget(value_label)
        root.addLayout(row)
        self._gesture_sliders.append((key, slider, scale))

    def _on_reset_gestures(self) -> None:
        for key in user_prefs.GESTURE_KEYS:
            user_prefs.set_value(key, user_prefs.DEFAULTS[key])
        self._gesture_check.setChecked(user_prefs.DEFAULTS["gestures_enabled"])
        self._resume_combo.setCurrentIndex(max(self._resume_combo.findData(user_prefs.DEFAULTS["gesture_resume_mode"]), 0))
        for key, slider, scale in self._gesture_sliders:
            default = user_prefs.DEFAULTS[key]
            slider.setValue(int(round(default * scale)) if scale != 1 else int(default))

    # -- personalization -------------------------------------------------------
    def _add_look_slider(self, root, text, key, lo, hi, suffix):
        row = QHBoxLayout()
        label = QLabel(text)
        value = QLabel()
        value.setMinimumWidth(48)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setMinimumWidth(110)
        slider.setValue(int(user_prefs.get(key)))
        value.setText(f"{slider.value()}{suffix}")

        def changed(v):
            value.setText(f"{v}{suffix}")
            user_prefs.set_value(key, int(v))
            self._look_timer.start(350)      # apply once the slider settles

        slider.valueChanged.connect(changed)
        row.addWidget(label, 1)
        row.addWidget(slider)
        row.addWidget(value)
        root.addLayout(row)
        slider._pref_key, slider._value_label, slider._suffix = key, value, suffix
        return slider

    def _apply_look(self) -> None:
        theme = user_prefs.get("theme")
        apply_theme(QApplication.instance(), theme)
        self.setStyleSheet(dialog_stylesheet(theme))
        self.look_changed.emit()

    def _refresh_swatches(self) -> None:
        for key, btn in self._swatches.items():
            colour = user_prefs.get(key)
            c = QColor(colour)
            dark = c.lightness() < 128
            btn.setStyleSheet(f"background: {colour}; color: {'white' if dark else 'black'};")

    def _pick_colour(self, key: str) -> None:
        chosen = QColorDialog.getColor(QColor(user_prefs.get(key)), self, "Pick a colour")
        if not chosen.isValid():
            return
        user_prefs.set_value(key, chosen.name().upper())
        self._refresh_swatches()
        if user_prefs.get("theme") == "custom":
            self._apply_look()

    def _use_custom_theme(self) -> None:
        user_prefs.set_value("theme", "custom")
        self._saved_theme = "custom"
        self._theme_combo.blockSignals(True)
        self._theme_combo.setCurrentIndex(max(self._theme_combo.findData("custom"), 0))
        self._theme_combo.blockSignals(False)
        self._preview_box.setVisible(False)
        self._apply_look()

    _LOOK_KEYS = ("theme", "font_scale", "window_opacity", "custom_accent1", "custom_accent2", "custom_bg")

    def _presets(self) -> dict:
        try:
            data = json.loads(user_prefs.get("presets_json"))
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def _refresh_presets(self) -> None:
        self._preset_combo.clear()
        names = sorted(self._presets())
        for name in names:
            self._preset_combo.addItem(name)
        if not names:
            self._preset_combo.addItem("(no saved looks yet)")

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save look", "Name for this look:")
        name = name.strip()
        if not ok or not name:
            return
        presets = self._presets()
        presets[name] = {k: user_prefs.get(k) for k in self._LOOK_KEYS}
        user_prefs.set_value("presets_json", json.dumps(presets))
        self._refresh_presets()
        self._preset_combo.setCurrentIndex(max(self._preset_combo.findText(name), 0))

    def _apply_preset(self) -> None:
        preset = self._presets().get(self._preset_combo.currentText())
        if not preset:
            return
        for key in self._LOOK_KEYS:
            if key in preset and type(preset[key]) is type(user_prefs.DEFAULTS[key]):
                user_prefs.set_value(key, preset[key])
        self._font_slider.blockSignals(True)
        self._font_slider.setValue(int(user_prefs.get("font_scale")))
        self._font_slider.blockSignals(False)
        self._opacity_slider.blockSignals(True)
        self._opacity_slider.setValue(int(user_prefs.get("window_opacity")))
        self._opacity_slider.blockSignals(False)
        for slider in (self._font_slider, self._opacity_slider):
            slider._value_label.setText(f"{slider.value()}{slider._suffix}")
        self._saved_theme = user_prefs.get("theme")
        self._theme_combo.blockSignals(True)
        self._theme_combo.setCurrentIndex(max(self._theme_combo.findData(self._saved_theme), 0))
        self._theme_combo.blockSignals(False)
        self._preview_box.setVisible(False)
        self._refresh_swatches()
        self._apply_look()

    def _delete_preset(self) -> None:
        name = self._preset_combo.currentText()
        presets = self._presets()
        if name in presets:
            del presets[name]
            user_prefs.set_value("presets_json", json.dumps(presets))
            self._refresh_presets()

    def _preview_personality_voice(self) -> None:
        from ui.accounts_dialog import _TaskWorker
        personality = self._personality_combo.currentData()
        choice = voice_cfg.resolve(personality)
        sample = voice_cfg.sample_text(personality)

        def _speak():
            if choice["edge"]:
                from voice.edge_tts_backend import EdgeTTS, EdgeTTSError
                try:
                    EdgeTTS(voice=choice["voice"], rate=choice["rate"], pitch=choice["pitch"]).speak(sample)
                    return True, ""
                except EdgeTTSError as e:
                    note = f"The natural voice isn't available ({e}). Playing the offline voice instead."
                else:
                    note = ""
            else:
                note = ""
            from voice.text_to_speech import TextToSpeech
            TextToSpeech(voice_gender=choice["gender"]).speak(sample)
            return (not note), note

        self._voice_preview_btn.setEnabled(False)
        self._voice_preview_btn.setText("Playing…")
        self._preview_worker = _TaskWorker(_speak, self)

        def _finished(ok, message):
            self._voice_preview_btn.setEnabled(True)
            self._voice_preview_btn.setText("▶ Preview the current personality's voice")
            if message:
                QMessageBox.information(self, "Voice preview", message)

        self._preview_worker.done.connect(_finished)
        self._preview_worker.start()

    # -- connected device ----------------------------------------------------
    def _refresh_device_status(self) -> None:
        dev = devices.connected_id()
        self._device_status.setText(f"✅ Connected: {devices.mask(dev)}" if dev else "Not connected")
        self._device_disconnect_btn.setEnabled(bool(dev))
        self._test_call_btn.setEnabled(bool(dev))

    def _connect_device(self) -> None:
        ok, message = devices.connect(self._device_code.text())
        if ok:
            self._device_code.clear()
        self._refresh_device_status()
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Connect device", message)

    def _open_compute(self) -> None:
        from ui.compute_ui import ComputeDialog
        ComputeDialog(self).exec()

    def _disconnect_device(self) -> None:
        devices.disconnect()
        self._refresh_device_status()

    def _make_code(self) -> None:
        code = devices.new_code()
        channel = devices.topic_for(devices.decode_code(code))
        QMessageBox.information(
            self, "New device code",
            f"Device code:\n{code}\n\n"
            "Until the EV phone app is ready, set the phone up like this:\n"
            "1. Install the free ntfy app on the phone.\n"
            f"2. Tap + and subscribe to the channel:  {channel}\n"
            "3. In the app's settings allow notifications and turn off battery optimisation for it.\n"
            "4. Type the device code above here and press Connect.")
        self._device_code.setText(code)

    def _test_call(self) -> None:
        self._test_call_btn.setEnabled(False)
        self._test_call_btn.setText("Ringing…")
        self._call_worker = _TaskWorker(
            lambda: devices.ring_phone("This is a test ring from EV. Your phone is connected."), self)

        def _finished(ok, message):
            self._test_call_btn.setEnabled(True)
            self._test_call_btn.setText("Send a test ring")
            (QMessageBox.information if ok else QMessageBox.warning)(self, "Test ring", message)

        self._call_worker.done.connect(_finished)
        self._call_worker.start()

    # -- clipboard / doctor ----------------------------------------------------
    def _ask_ai(self, text: str) -> None:
        self.accept()
        self.ask_ai_requested.emit(text)

    def _open_insights(self) -> None:
        from ui.insights_dialog import InsightsDialog
        InsightsDialog(self).exec()

    def _open_finder(self) -> None:
        from ui.file_finder_dialog import FileFinderDialog
        FileFinderDialog(self).exec()

    def _open_error_doctor(self) -> None:
        from ui.error_doctor_dialog import ErrorDoctorDialog
        video_on = bool(getattr(self.parent(), "_video_mode_on", False))
        ErrorDoctorDialog(video_on, self).exec()

    def _on_replay_intro(self) -> None:
        self.accept()                       # close Settings so the animation is visible
        self.replay_intro_requested.emit()

    def _on_reset_settings(self) -> None:
        answer = QMessageBox.question(
            self, "Reset settings",
            "Put every switch on this page back to its default?\n\n"
            "Your API keys, email account and password are not affected.",
        )
        if answer != QMessageBox.Yes:
            return
        for key, value in user_prefs.DEFAULTS.items():
            user_prefs.set_value(key, value)
        self._apply_prefs_live()
        QMessageBox.information(self, "Reset settings", "Settings reset to defaults.")

    # -- search ------------------------------------------------------------------
    _SEARCH_ALIASES = {
        "PROFILE": "profile focus study gaming work preset mode",
        "AI, EMAIL & VOICE": "api key provider model email outlook gmail voice tts speech wake word account chatgpt openai",
        "APPEARANCE": "theme dark light mode colour color look preview crimson emerald violet ocean gold sunset midnight mono red green purple blue",
        "GESTURE CONTROL": "gesture gestures hand camera webcam video swipe zoom pinch volume tab desktop pause resume fist palm finger fingers threshold cooldown sensitivity",
        "PERSONALITY": "personality tone style professional friendly humorous funny voice voices character speaker accent male female",
        "PERSONALIZATION": "personalization personalize font text size opacity transparency custom theme colour color preset accent background",
        "APP USAGE INSIGHTS": "app usage insights screen time tracking apps time spent top apps coding study browsing entertainment history privacy",
        "FILE FINDER": "file finder search find files documents images pdf python arduino downloads folder index",
        "FOCUS MODE": "focus mode study block distractions youtube scratch discord instagram sites apps",
        "QUICK ACTIONS": "quick actions commands macro automation study mode chain open apps sites",
        "CLIPBOARD ASSISTANT": "clipboard copy paste summarize rewrite text",
        "ERROR DOCTOR": "error doctor fix problem troubleshoot diagnose camera missing package",
        "CONNECTED DEVICE": "device connect pair phone mobile code call ring ntfy shutdown switch off computer",
        "BEHAVIOUR": "sound hover speak voice tray hotkey offline always on top briefing observe interval mute",
        "DATA": "save conversation data folder",
        "STARTUP FACE CHECK": "face password camera security login unlock",
        "PRIVACY": "privacy microphone mic camera permissions history security",
        "ACTIVITY LOG": "log logs error errors debug",
        "SYSTEM & ABOUT": "version about update updates diagnostics export import reset defaults backup",
    }

    @staticmethod
    def _widgets_in(item):
        if item.widget() is not None:
            yield item.widget()
        elif item.layout() is not None:
            for k in range(item.layout().count()):
                yield from SettingsDialog._widgets_in(item.layout().itemAt(k))

    def _index_groups(self, root) -> list:
        """Split the page into sections (separated by divider lines) and note
        each one's searchable text, for the search box."""
        groups, current = [], {"widgets": [], "text": [], "title": ""}
        for index in range(root.count()):
            for widget in self._widgets_in(root.itemAt(index)):
                current["widgets"].append(widget)
                if isinstance(widget, QLabel):
                    current["text"].append(widget.text())
                    if widget.property("role") == "section":
                        current["title"] = widget.text()
                elif isinstance(widget, (QCheckBox, QPushButton)):
                    current["text"].append(widget.text())
                elif isinstance(widget, QComboBox):
                    current["text"].extend(widget.itemText(n) for n in range(widget.count()))
                if isinstance(widget, QFrame) and widget.frameShape() == QFrame.HLine:
                    groups.append(current)
                    current = {"widgets": [], "text": [], "title": ""}
        if current["widgets"]:
            groups.append(current)
        for group in groups:
            group["haystack"] = (" ".join(group["text"]) + " " + group["title"] + " "
                                 + self._SEARCH_ALIASES.get(group["title"], "")).lower()
        return groups

    def _apply_search(self, query: str) -> None:
        words = query.lower().split()
        for group in self._search_groups:
            show = all(w in group["haystack"] for w in words)
            for widget in group["widgets"]:
                widget.setVisible(show and not (widget is self._preview_box and not self._theme_changed_pending()))

    def _theme_changed_pending(self) -> bool:
        return self._theme_combo.currentData() != self._saved_theme

    def _on_always_on_top(self, enabled: bool) -> None:
        user_prefs.set_value("always_on_top", enabled)
        self.always_on_top_changed.emit(enabled)

    def _on_create_shortcut(self) -> None:
        import contextlib
        import io
        from scripts.create_shortcut import main as make_shortcut
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = make_shortcut()
        text = buffer.getvalue().strip() or "Done."
        (QMessageBox.information if code == 0 else QMessageBox.warning)(self, "EV shortcut", text)

    def _on_hotkey_toggled(self, enabled: bool) -> None:
        user_prefs.set_value("global_hotkey", enabled)
        self.global_hotkey_changed.emit(enabled)

    def _on_tray_toggled(self, enabled: bool) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon
        if enabled and not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_check.blockSignals(True)
            self._tray_check.setChecked(False)
            self._tray_check.blockSignals(False)
            QMessageBox.information(self, "System tray", "This system has no tray available.")
            return
        user_prefs.set_value("minimize_to_tray", enabled)
        self.minimize_to_tray_changed.emit(enabled)

    def _on_auto_cache(self, enabled: bool) -> None:
        user_prefs.set_value("auto_clear_pycache", enabled)
        # Takes effect for the rest of this run too, not just next launch.
        sys.dont_write_bytecode = enabled

    def _on_save_conversation(self) -> None:
        view = getattr(self.parent(), "conversation_view", None)
        text = view.toPlainText() if view is not None else ""
        if not text.strip():
            QMessageBox.information(self, "Save conversation", "There's no conversation to save yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save conversation", "ev_ai_conversation.txt", "Text files (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            QMessageBox.warning(self, "Save conversation", f"Couldn't save the file: {e}")

    def _on_clear_cache_now(self) -> None:
        removed = clear_pycache(APP_ROOT)
        QMessageBox.information(
            self, "Clear __pycache__",
            f"Removed {removed} __pycache__ folder{'s' if removed != 1 else ''}.",
        )

    # -- internal ---------------------------------------------------------
    def _on_open_privacy(self) -> None:
        from ui.privacy_dialog import PrivacyDialog
        PrivacyDialog(self.parent()).exec()

    def _on_view_log(self) -> None:
        log_box = QDialog(self)
        log_box.setWindowTitle(f"{settings.APP_NAME} — Activity log")
        log_box.setStyleSheet(self.styleSheet())
        log_box.resize(620, 440)
        layout = QVBoxLayout(log_box)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Consolas", 9))
        text.setStyleSheet(
            "QTextEdit { background: rgba(6,12,20,235); color: #c8e4ff; "
            "border: 1px solid rgba(120,190,255,60); border-radius: 6px; }"
        )
        layout.addWidget(text)

        def _refresh():
            # Only rewrite + rescroll when there's actually new content —
            # otherwise this timer would fight the user's own scrollbar
            # drags every second for no reason.
            content = LOG.get_text()
            if text.toPlainText() != content:
                was_at_bottom = text.verticalScrollBar().value() >= text.verticalScrollBar().maximum() - 4
                text.setPlainText(content)
                if was_at_bottom:
                    text.verticalScrollBar().setValue(text.verticalScrollBar().maximum())

        _refresh()
        refresh_timer = QTimer(log_box)
        refresh_timer.timeout.connect(_refresh)
        refresh_timer.start(1000)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy all")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(text.toPlainText()))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(log_box.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        log_box.exec()

    def _on_view_changelog(self) -> None:
        try:
            content = _CHANGELOG_PATH.read_text(encoding="utf-8")
        except OSError:
            content = "No update log found — CHANGELOG.md is missing from the project folder."

        log_box = QDialog(self)
        log_box.setWindowTitle(f"{settings.APP_NAME} — Update log")
        log_box.setStyleSheet(self.styleSheet())
        log_box.resize(620, 440)
        layout = QVBoxLayout(log_box)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setMarkdown(content)
        text.setStyleSheet(
            "QTextEdit { background: rgba(6,12,20,235); color: #d8eeff; "
            "border: 1px solid rgba(120,190,255,60); border-radius: 6px; }"
        )
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(log_box.accept)
        layout.addWidget(close_btn)

        log_box.exec()

    @staticmethod
    def _copy_to_clipboard(text: str) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)


    def _refresh_face_status(self) -> None:
        from core.face_auth import is_enrolled, has_password_set
        enabled = settings.FACE_AUTH_ENABLED
        enrolled = is_enrolled()
        has_pw = has_password_set()
        lines = [f"Check on startup: {'enabled' if enabled else 'disabled'}"]
        lines.append(f"Enrolled face: {'yes' if enrolled else 'no (press Face recognition setup)'}")
        lines.append(f"Password fallback: {'set' if has_pw else 'not set'}")
        self._face_status.setText("\n".join(lines))
        self._face_status.setStyleSheet("color: #8fd0ff; font-size: 11px;")
        if hasattr(self, "_face_toggle_btn"):
            self._face_toggle_btn.setText("Turn startup check OFF" if enabled else "Turn startup check ON")
            self._face_toggle_btn.setEnabled(enrolled or enabled)

    def _on_face_toggle(self) -> None:
        from core.env_file import update_env
        from core.face_auth import has_password_set
        turning_on = not settings.FACE_AUTH_ENABLED
        if turning_on and not has_password_set():
            QMessageBox.information(
                self, "Face check",
                "Tip: set a password fallback too, so you can still get in if the camera can't recognise you.")
        update_env({"FACE_AUTH_ENABLED": "true" if turning_on else "false"})
        QMessageBox.information(self, "Face check",
                                f"Startup face check will be {'ON' if turning_on else 'OFF'} the next time EV AI starts.")
        # settings is read once at startup, so show the new state until then
        settings.FACE_AUTH_ENABLED = turning_on
        self._refresh_face_status()

    def _on_face_setup(self) -> None:
        """Captures ~25 photos of the owner from the webcam and trains the recogniser."""
        box = QDialog(self)
        box.setWindowTitle("Face recognition setup")
        box.setStyleSheet(self.styleSheet())
        box.setMinimumWidth(420)
        layout = QVBoxLayout(box)
        info = QLabel(
            "Sit in good light and look at your webcam. When you press Start, slowly turn your head "
            "a little left, right, up and down. It takes about 20-30 seconds. Photos stay on this computer.")
        info.setWordWrap(True)
        layout.addWidget(info)
        bar = QProgressBar()
        bar.setRange(0, 25)
        bar.setValue(0)
        layout.addWidget(bar)
        status = QLabel("")
        status.setWordWrap(True)
        layout.addWidget(status)
        row = QHBoxLayout()
        start_btn = QPushButton("Start")
        close_btn = QPushButton("Cancel")
        row.addWidget(start_btn)
        row.addWidget(close_btn)
        layout.addLayout(row)
        close_btn.clicked.connect(box.reject)

        worker_holder = {}

        def _done(result: dict) -> None:
            start_btn.setEnabled(True)
            close_btn.setText("Close")
            if "error" in result:
                status.setText(f"Setup failed: {result['error']}")
                return
            bar.setValue(bar.maximum())
            status.setText(f"Done. Your face was saved from {result['samples']} photos.")
            self._refresh_face_status()
            if not settings.FACE_AUTH_ENABLED:
                answer = QMessageBox.question(
                    box, "Face check", "Turn on the startup face check now? (It applies the next time EV AI starts.)")
                if answer == QMessageBox.Yes:
                    from core.env_file import update_env
                    update_env({"FACE_AUTH_ENABLED": "true"})
                    settings.FACE_AUTH_ENABLED = True
                    self._refresh_face_status()

        def _start() -> None:
            start_btn.setEnabled(False)
            bar.setValue(0)
            status.setText("Look at the camera and slowly move your head…")
            worker = _FaceEnrollWorker(box)
            worker.progress.connect(lambda cur, total: (bar.setMaximum(total), bar.setValue(cur)))
            worker.finished_with.connect(_done)
            worker_holder["w"] = worker
            worker.start()

        start_btn.clicked.connect(_start)
        box.exec()
        worker = worker_holder.get("w")
        if worker is not None and worker.isRunning():
            worker.wait(15000)

    def _on_set_password(self) -> None:
        from core.face_auth import set_password

        password_box = QDialog(self)
        password_box.setWindowTitle("Set password fallback")
        password_box.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(password_box)
        layout.addWidget(QLabel("New password (min 4 characters):"))
        pw1 = QLineEdit()
        pw1.setEchoMode(QLineEdit.Password)
        layout.addWidget(pw1)
        layout.addWidget(QLabel("Confirm:"))
        pw2 = QLineEdit()
        pw2.setEchoMode(QLineEdit.Password)
        layout.addWidget(pw2)
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        ok_btn.clicked.connect(password_box.accept)
        cancel_btn.clicked.connect(password_box.reject)

        if password_box.exec() != QDialog.Accepted:
            return

        if pw1.text() != pw2.text():
            QMessageBox.warning(self, "Password fallback", "Those passwords didn't match — nothing was changed.")
            return

        result = set_password(pw1.text())
        if "error" in result:
            QMessageBox.warning(self, "Password fallback", result["error"])
        else:
            QMessageBox.information(self, "Password fallback", "Saved — this will work as a fallback on the startup screen.")
        self._refresh_face_status()

    def _on_enable_autostart(self) -> None:
        self._run_autostart_script(enable=True)

    def _on_disable_autostart(self) -> None:
        self._run_autostart_script(enable=False)

    @staticmethod
    def _run_autostart_script(enable: bool) -> None:
        if enable:
            from scripts.install_autostart import main as run
        else:
            from scripts.uninstall_autostart import main as run

        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                code = run()
        except Exception as e:  # pragma: no cover — defensive, scripts are small
            code = 1
            buffer.write(str(e))

        output = buffer.getvalue().strip() or ("Done." if code == 0 else "Something went wrong.")
        title = "Enable autostart" if enable else "Disable autostart"
        if code == 0:
            QMessageBox.information(None, title, output)
        else:
            QMessageBox.warning(None, title, output)
