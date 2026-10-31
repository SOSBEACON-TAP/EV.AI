"""
ui/main_window.py
------------------
The EV AI dashboard window.
- Lays out the full futuristic UI (top bar, AI core, status panels,
  conversation panel, command input, quick-action buttons).
- Stage 1: state machine + animations, verified with a stub text pipeline.
- Stage 2: real voice input/output — wake word ("Hey EV"), clap-to-activate,
  and text-to-speech replies — layered on without changing the layout code.
- A real AI brain (Stage 3) and real tools (Stage 4-6) will plug into
  `handle_user_input()` later, same principle.

No network calls except what the voice modules make to the speech API;
everything else here is self-contained.
"""

import datetime
import html

import psutil
import hashlib

from PySide6.QtCore import Qt, QTimer, Signal, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QTextEdit, QLineEdit, QPushButton, QSizePolicy,
    QButtonGroup, QFileDialog, QMenu, QApplication,
)

from core import user_prefs
from ui.tray import TrayController
from ui.hotkey import GlobalHotkey
from ui.song_panel import SongPanel
from ui.video_view import VideoViewWindow
from ui.focus_mode import FocusMode
from ui.usage_tracker import UsageTracker
from core.offline import OfflineAssistant
from core.brain_worker import ImageWorker
from core.state import AIState
from ui.animations import AICoreWidget
from ui.system_monitor import SystemMonitorPanel
from ui.hud_overlay import HUDOverlayWidget
from ui.settings_dialog import SettingsDialog
from ui.widgets import HoverButton
from config import settings
from tools import reminders as reminder_tools
from tools import memory as memory_tools

# Voice dependencies (speech_recognition, pyaudio, pyttsx3) are optional at
# import time — if they're missing or fail to load on this machine, EV AI
# should still start up with voice features simply disabled, rather than
# crashing. See requirements.txt for what Stage 2 needs installed.
try:
    from voice.listener_thread import VoiceListenerThread
    from voice.speech_worker import SpeechWorker
    from voice.clap_detector import ClapDetectorThread
    VOICE_AVAILABLE = True
    VOICE_IMPORT_ERROR = ""
except Exception as e:  # broad on purpose — any import-time failure disables voice, doesn't crash the app
    VoiceListenerThread = None
    SpeechWorker = None
    ClapDetectorThread = None
    VOICE_AVAILABLE = False
    VOICE_IMPORT_ERROR = str(e)

# Same pattern for the AI brain (Stage 3) — the anthropic package might not
# be installed yet, or might fail to import for some other reason. Either
# way, EV AI should start up and fall back to a "no brain configured"
# message rather than crashing.
try:
    from core.brain import Brain
    from core.brain_worker import BrainWorker
    from core.router import ToolRouter
    from core.vision_worker import VisionWorker
    from core.modes import Mode
    AI_AVAILABLE = True
    AI_IMPORT_ERROR = ""
except Exception as e:
    Brain = None
    BrainWorker = None
    ToolRouter = None
    VisionWorker = None
    Mode = None
    AI_AVAILABLE = False
    AI_IMPORT_ERROR = str(e)

# Video mode (Stage 10: pinch-to-zoom gesture control) needs mediapipe on
# top of opencv — a heavier, separate dependency most people won't have
# installed by default, so this follows the same "degrade, don't crash"
# pattern as voice/AI above. GestureWorker itself re-checks and reports
# the same way when actually started, in case it's missing at import
# time here but becomes available later without a restart being obvious.
try:
    from core.gesture_worker import GestureWorker
    GESTURE_AVAILABLE = True
except Exception:
    GestureWorker = None
    GESTURE_AVAILABLE = False


def glass_panel(accent: str | None = None) -> QFrame:
    """Factory for a consistently-styled translucent panel.

    accent: "red", "blue", or None for the neutral look. Drives the
    QSS selectors QFrame#GlassPanel[accent="red"/"blue"] in dark_theme.qss.
    """
    frame = QFrame()
    frame.setObjectName("GlassPanel")
    if accent:
        frame.setProperty("accent", accent)
    return frame


_COMPACT_BTN = "QPushButton { padding: 5px 4px; letter-spacing: 0px; font-size: 11px; }"


class MainWindow(QMainWindow):
    reminder_fired = Signal(str)  # emitted from tools/reminders.py's background timer thread

    def __init__(self):
        super().__init__()
        self.setWindowTitle(settings.APP_NAME)
        self.resize(1180, 720)
        self.setObjectName("RootBackground")
        if user_prefs.get("always_on_top"):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self._tray = TrayController(self)
        self._tray.set_enabled(user_prefs.get("minimize_to_tray"))
        self._hotkey = GlobalHotkey(self.toggle_visibility)
        self._focus = FocusMode(self)
        self._focus.blocked.connect(self._on_focus_blocked)
        self._focus_worker = None
        self._usage = UsageTracker(self)
        self._usage.start()
        self._insights_dlg = None
        self._finder_dlg = None
        if user_prefs.get("global_hotkey"):
            self._hotkey.enable()
        if user_prefs.get("auto_check_updates") and settings.UPDATE_CHECK_URL:
            from ui.update_flow import StartupCheck
            self._startup_update_check = StartupCheck(self._on_update_available, self)
            QTimer.singleShot(8000, self._startup_update_check.start)
        if user_prefs.get("briefing_on_start"):
            QTimer.singleShot(4000, lambda: self.handle_user_input("Give me my morning briefing"))

        self._state = AIState.IDLE
        self._listener_thread = None   # VoiceListenerThread, created on demand
        self._speech_worker = None     # SpeechWorker, created per speak() call
        self._clap_detector = None     # ClapDetectorThread, runs whenever voice listening is off
        self._brain_worker = None      # BrainWorker, created per ask() call
        # Kept as its own attribute (not just handed to Brain) so the
        # Stage 8 scheduled-task poller below can also dispatch tool
        # calls through the same router instance.
        self._tool_router = ToolRouter() if AI_AVAILABLE else None
        self._brain = Brain(router=self._tool_router) if AI_AVAILABLE else None
        self._offline = OfflineAssistant(self._tool_router) if self._tool_router is not None else None
        self._last_text = ""
        self._busy_disable_widgets = []  # populated in _build_ui(); disabled while a brain request is in flight

        # Observation mode (screen watching)
        self._observe_timer = None      # QTimer, created on demand
        self._vision_worker = None      # VisionWorker, created per screenshot
        self._last_screen_hash = None   # skip sending unchanged screens
        self._observing = False

        # Video mode (pinch-to-zoom gesture control)
        self._gesture_worker = None     # GestureWorker, created on demand
        self._video_mode_on = False
        self._video_view = None         # camera window with the HUD rings
        self._song_panel = None
        self._image_worker = None
        self.setAcceptDrops(True)
        self._current_mode = Mode.NORMAL if AI_AVAILABLE else None

        # Full-screen HUD overlay (Automatic, Serious, Study, Observation)
        # — shown instead of the full dashboard. Created lazily on first use.
        self._hud_overlay = None
        self._recent_commands = []  # last few things the user typed/said

        self._jarvis_on = False
        self._pre_jarvis_mode = None
        self._phone_call_sent = False
        self._build_ui()
        self._hook_shutdown_call()
        try:
            from ui.compute_ui import controller
            controller().start()
        except Exception as e:
            print(f"[EV AI] Compute unavailable: {e}")
        if user_prefs.get("jarvis_ui"):
            QTimer.singleShot(0, lambda: self._apply_jarvis_ui(True, announce=False))
        self._apply_state(AIState.IDLE)

        if not VOICE_AVAILABLE:
            self.mic_status_label.setText("MIC: VOICE DEPS NOT INSTALLED")
            self.mic_toggle_btn.setEnabled(False)
            self.mic_toggle_btn.setToolTip(
                f"Voice features unavailable: {VOICE_IMPORT_ERROR}\n"
                "Run: pip install -r requirements.txt"
            )

        # Live system clock + resource usage, refreshed on a timer.
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._refresh_metrics)
        self._clock_timer.start(settings.UI_REFRESH_MS)
        self._refresh_metrics()

        self._append_conversation("EV", "SYSTEM ONLINE. READY.")

        self.reminder_fired.connect(self._on_reminder_fired)
        reminder_tools.register_callback(self.reminder_fired.emit)
        reminder_tools.restore()   # re-arm reminders saved by an earlier run

        # Stage 8: recurring scheduled tasks (daily/weekly) persist in
        # SQLite via core/automation.py and are checked here rather than
        # with a threading.Timer like the one-off set_timer tool — a
        # polling check is simpler to keep correct across app restarts
        # (a threading.Timer set for "tomorrow at 9am" wouldn't survive
        # a restart; checking "is it 9am right now" every 20s does).
        if AI_AVAILABLE:
            self._schedule_timer = QTimer(self)
            self._schedule_timer.timeout.connect(self._check_scheduled_tasks)
            self._schedule_timer.start(20_000)

        if VOICE_AVAILABLE:
            self._start_clap_detector()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self._central = central
        central.setObjectName("RootBackground")
        central.setAttribute(Qt.WA_StyledBackground, True)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)
        body_layout.setSpacing(16)

        body_layout.addWidget(self._build_left_column(), 2)
        body_layout.addWidget(self._build_center_column(), 3)
        body_layout.addWidget(self._build_right_column(), 2)

        root.addWidget(body, 1)
        self.setCentralWidget(central)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)

        logo = QLabel(settings.APP_NAME)
        logo.setObjectName("LogoLabel")
        self._logo_label = logo
        layout.addWidget(logo)

        layout.addStretch(1)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("SettingsButton")
        self.settings_btn.setFixedSize(32, 32)
        self.settings_btn.setToolTip("Settings")
        # Styled via #SettingsButton in the theme .qss files, so it follows dark/light.
        self.settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(self.settings_btn)

        return bar

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.always_on_top_changed.connect(self.set_always_on_top)
        dialog.minimize_to_tray_changed.connect(self._set_minimize_to_tray)
        dialog.global_hotkey_changed.connect(self._set_global_hotkey)
        dialog.profile_applied.connect(self._apply_profile)
        dialog.replay_intro_requested.connect(self.replay_intro)
        dialog.quick_actions_requested.connect(self._open_quick_actions)
        dialog.focus_toggle_requested.connect(self._toggle_focus_mode)
        dialog.ask_ai_requested.connect(self._ask_ai_text)
        dialog.look_changed.connect(self._apply_window_look)
        dialog.exec()

    # ------------------------------------------------------------------
    # Quick Actions, Focus Mode, personalization, clipboard helpers
    # ------------------------------------------------------------------
    def _open_quick_actions(self) -> None:
        from ui.quick_actions import QuickActionsDialog
        QuickActionsDialog(self._tool_router, self).exec()

    def _open_insights_window(self) -> None:
        from ui.insights_dialog import InsightsDialog
        if self._insights_dlg is None:
            self._insights_dlg = InsightsDialog(self)
            self._insights_dlg.setAttribute(Qt.WA_DeleteOnClose, True)
            self._insights_dlg.destroyed.connect(lambda *_: setattr(self, "_insights_dlg", None))
        self._insights_dlg.show()
        self._insights_dlg.raise_()

    def _open_finder_window(self) -> None:
        from ui.file_finder_dialog import FileFinderDialog
        if self._finder_dlg is None:
            self._finder_dlg = FileFinderDialog(self)
            self._finder_dlg.setAttribute(Qt.WA_DeleteOnClose, True)
            self._finder_dlg.destroyed.connect(lambda *_: setattr(self, "_finder_dlg", None))
        self._finder_dlg.show()
        self._finder_dlg.raise_()

    def _ask_ai_text(self, text: str) -> None:
        """Send a prepared request as if it had been typed in the command box."""
        self.show()
        self.raise_()
        self.command_input.setText(text)
        self._on_send_clicked()

    def _apply_window_look(self) -> None:
        pct = int(user_prefs.get("window_opacity"))
        self.setWindowOpacity(max(0.6, min(1.0, pct / 100.0)))

    def _toggle_focus_mode(self) -> None:
        if self._focus.running:
            self._focus.stop()
            self.focus_toggle_btn.setText("🎯 FOCUS: OFF")
            self.focus_toggle_btn.setChecked(False)
            if AI_AVAILABLE and Mode is not None:
                self._set_mode(Mode.NORMAL)
            self._append_conversation("EV", "(Focus Mode off.)")
            return
        self.focus_toggle_btn.setText("🎯 FOCUS: ON")
        self.focus_toggle_btn.setChecked(True)
        if AI_AVAILABLE and Mode is not None:
            self._set_mode(Mode.STUDY)       # the quiet corner mode, now called Focus
        chain = str(user_prefs.get("focus_chain")).strip().lower()
        started = ""
        if chain and self._tool_router is not None:
            from tools import automation as automation_tools
            from ui.quick_actions import _RunWorker
            if automation_tools.get_store().get_chain(chain) is not None:
                self._focus_worker = _RunWorker(self._tool_router, chain, self)
                self._focus_worker.start()
                started = f" Running “{chain}”."
            else:
                started = f" (No Quick Action named “{chain}” yet — make one in Settings → Quick Actions.)"
        self._focus.start(user_prefs.get("focus_blocked"), user_prefs.get("focus_action"))
        what = "closed" if user_prefs.get("focus_action") != "warn" else "flagged"
        self._append_conversation("EV", f"(Focus Mode on.{started} Blocked sites/apps will be {what}: "
                                        f"{user_prefs.get('focus_blocked')}.)")

    def _on_focus_blocked(self, site: str, closed: bool) -> None:
        verb = "Closed" if closed else "Spotted"
        self._append_conversation("EV", f"(Focus Mode: {verb} {site.title()}. Back to work!)")

    def replay_intro(self) -> None:
        """Play the logo -> core intro animation again (Settings > Replay intro animation)."""
        from ui.transition import play_startup_transition
        QTimer.singleShot(200, lambda: setattr(self, "_intro", play_startup_transition(self)))

    def _on_update_available(self, info: dict) -> None:
        self._append_conversation(
            "EV", f"(A new version of {settings.APP_NAME} is available: {info['version']}. "
                  "Open ⚙ Settings → Check for updates to install it.)")

    def privacy_snapshot(self) -> dict:
        """Live status for Settings -> Privacy center."""
        listening = self._listener_thread is not None and self._listener_thread.isRunning()
        claps = self._clap_detector is not None and self._clap_detector.isRunning()
        if listening:
            mic = "Listening (voice)"
        elif claps:
            mic = "Clap detection on"
        else:
            mic = "Off"
        if self._video_mode_on:
            camera = "In use (Video mode)"
        else:
            camera = "Off" + (" — used at start-up for the face check" if settings.FACE_AUTH_ENABLED else "")
        if self._observing:
            screen = f"On — screenshot every {user_prefs.get('observe_interval_s')}s"
        else:
            screen = "Off"
        router = self._tool_router
        confirm = sorted(t.name for t in router.list_tools() if t.requires_confirmation) if router else []
        return {"mic": mic, "camera": camera, "screen": screen, "confirm_tools": confirm}

    def toggle_visibility(self) -> None:
        """Global hotkey: hide if EV is in front, otherwise bring it up."""
        if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
            if self._tray.is_active():
                self.hide()
            else:
                self.showMinimized()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _apply_profile(self, name: str) -> None:
        """Settings -> Profile: switch EV's mode (Study / Work / ...) and stop
        features the profile says should be off. The profile's switches
        were already saved and applied by the Settings dialog."""
        from core.profiles import PROFILES
        profile = PROFILES.get(name)
        if profile is None:
            return
        if profile.get("stop_observe") and self._observing:
            self._stop_observation()
        if profile.get("stop_video") and self._video_mode_on:
            self._stop_video_mode()
        if AI_AVAILABLE and Mode is not None:
            try:
                self._set_mode(Mode(profile["mode"]))
            except ValueError:
                pass
        self._append_conversation("EV", f"({name} profile on.)")

    def _set_global_hotkey(self, enabled: bool) -> bool:
        if enabled:
            return self._hotkey.enable()
        self._hotkey.disable()
        return True

    def _set_minimize_to_tray(self, enabled: bool) -> bool:
        return self._tray.set_enabled(enabled)

    def allow_close(self) -> None:
        """Used by restart: really close even if minimize-to-tray is on."""
        self._tray.allow_close()

    def set_always_on_top(self, enabled: bool) -> None:
        # Changing a window flag hides the window; re-show it so toggling
        # the setting doesn't make the dashboard vanish.
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        if was_visible:
            self.show()

    def _build_left_column(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # Status panel
        status_panel = glass_panel(accent="red")
        sp_layout = QVBoxLayout(status_panel)
        sp_layout.setSpacing(3)
        sp_layout.setContentsMargins(12, 8, 12, 8)
        title = QLabel("STATUS")
        title.setObjectName("SectionTitle")
        sp_layout.addWidget(title)

        self.state_label = QLabel(AIState.IDLE.label)
        self.state_label.setObjectName("StateLabel")
        sp_layout.addWidget(self.state_label)

        self.mic_status_label = QLabel("MIC: OFF")
        self.mic_status_label.setObjectName("MetricCaption")
        sp_layout.addWidget(self.mic_status_label)

        self.last_heard_label = QLabel("LAST HEARD: —")
        self.last_heard_label.setObjectName("MetricCaption")
        self.last_heard_label.setWordWrap(True)
        sp_layout.addWidget(self.last_heard_label)

        self.internet_status_label = QLabel("INTERNET: CHECKING…")
        self.internet_status_label.setObjectName("MetricCaption")
        sp_layout.addWidget(self.internet_status_label)

        self.mic_toggle_btn = HoverButton("🎤 START VOICE")
        self.mic_toggle_btn.setMinimumHeight(30)
        self.mic_toggle_btn.setCheckable(True)
        self.mic_toggle_btn.clicked.connect(self._toggle_voice)
        sp_layout.addWidget(self.mic_toggle_btn)

        layout.addWidget(status_panel)

        # System metrics panel
        metrics_panel = glass_panel(accent="red")
        mp_layout = QGridLayout(metrics_panel)
        mp_layout.setVerticalSpacing(0)
        mp_layout.setContentsMargins(12, 8, 12, 8)
        mtitle = QLabel("SYSTEM")
        mtitle.setObjectName("SectionTitle")
        mp_layout.addWidget(mtitle, 0, 0, 1, 2)

        self.cpu_value = QLabel("--%")
        self.cpu_value.setObjectName("MetricValue")
        cpu_caption = QLabel("CPU")
        cpu_caption.setObjectName("MetricCaption")
        mp_layout.addWidget(self.cpu_value, 1, 0)
        mp_layout.addWidget(cpu_caption, 2, 0)

        self.ram_value = QLabel("--%")
        self.ram_value.setObjectName("MetricValue")
        ram_caption = QLabel("RAM")
        ram_caption.setObjectName("MetricCaption")
        mp_layout.addWidget(self.ram_value, 1, 1)
        mp_layout.addWidget(ram_caption, 2, 1)

        self.time_value = QLabel("--:--:--")
        self.time_value.setObjectName("MetricValue")
        time_caption = QLabel("TIME")
        time_caption.setObjectName("MetricCaption")
        mp_layout.addWidget(self.time_value, 3, 0)
        mp_layout.addWidget(time_caption, 4, 0)

        self.date_value = QLabel("----------")
        self.date_value.setObjectName("MetricValue")
        date_caption = QLabel("DATE")
        date_caption.setObjectName("MetricCaption")
        mp_layout.addWidget(self.date_value, 3, 1)
        mp_layout.addWidget(date_caption, 4, 1)

        layout.addWidget(metrics_panel)

        # Mode panel — mutually exclusive conversational presets, plus the
        # independent Observe toggle (can run alongside any mode).
        mode_panel = glass_panel(accent="red")
        mode_layout = QVBoxLayout(mode_panel)
        mode_layout.setSpacing(5)
        mode_layout.setContentsMargins(12, 8, 12, 8)
        mode_title = QLabel("MODE")
        mode_title.setObjectName("SectionTitle")
        mode_layout.addWidget(mode_title)

        # A QButtonGroup with setExclusive(True) makes the modes a true
        # radio-button set at the Qt level — clicking one always unchecks
        # every other one, so two modes can never show as active at once,
        # and there's no combo of modes (Observation is separate, by design
        # — see _should_use_hud below).
        self._mode_buttons = {}
        self._mode_button_group = QButtonGroup(self)
        self._mode_button_group.setExclusive(True)
        mode_grid = QGridLayout()
        mode_grid.setSpacing(5)
        mode_defs = [
            (Mode.NORMAL if AI_AVAILABLE else None, "NORMAL"),
            (Mode.AUTOMATIC if AI_AVAILABLE else None, "AUTOMATIC"),
            (Mode.SERIOUS if AI_AVAILABLE else None, "SERIOUS"),
            (Mode.DEEP_THINKING if AI_AVAILABLE else None, "DEEP THINKING"),
        ]
        for i, (mode, label) in enumerate(mode_defs):
            btn = HoverButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(30)
            btn.setStyleSheet(_COMPACT_BTN)
            if mode is not None:
                btn.setChecked(mode == Mode.NORMAL)
                btn.clicked.connect(lambda _, m=mode: self._set_mode(m))
                self._mode_buttons[mode] = btn
                self._mode_button_group.addButton(btn)
            else:
                btn.setEnabled(False)
            mode_grid.addWidget(btn, i // 2, i % 2)
        mode_layout.addLayout(mode_grid)

        tool_grid = QGridLayout()
        tool_grid.setSpacing(5)
        self.observe_toggle_btn = HoverButton("👁 OBSERVE: OFF")
        self.observe_toggle_btn.setCheckable(True)
        self.observe_toggle_btn.clicked.connect(self._toggle_observation)
        self.observe_toggle_btn.setEnabled(AI_AVAILABLE)
        self.observe_toggle_btn.setMinimumHeight(30)
        self.observe_toggle_btn.setStyleSheet(_COMPACT_BTN)
        tool_grid.addWidget(self.observe_toggle_btn, 0, 0)

        # Video mode: webcam hand-gesture control. Also toggleable from the
        # HUD's left panel while a HUD mode is up.
        self.video_toggle_btn = HoverButton("🎥 VIDEO: OFF")
        self.video_toggle_btn.setCheckable(True)
        self.video_toggle_btn.clicked.connect(self._toggle_video_mode)
        self.video_toggle_btn.setEnabled(GESTURE_AVAILABLE)
        self.video_toggle_btn.setMinimumHeight(30)
        self.video_toggle_btn.setStyleSheet(_COMPACT_BTN)
        tool_grid.addWidget(self.video_toggle_btn, 0, 1)

        # Song mode: small music-remote panel (play a song, media keys, volume).
        self.song_toggle_btn = HoverButton("🎵 SONG: OFF")
        self.song_toggle_btn.setCheckable(True)
        self.song_toggle_btn.clicked.connect(self._toggle_song_mode)
        self.song_toggle_btn.setMinimumHeight(30)
        self.song_toggle_btn.setStyleSheet(_COMPACT_BTN)
        tool_grid.addWidget(self.song_toggle_btn, 1, 0)

        # Focus Mode: study profile + your Quick Action + distraction blocking.
        self.focus_toggle_btn = HoverButton("🎯 FOCUS: OFF")
        self.focus_toggle_btn.setCheckable(True)
        self.focus_toggle_btn.clicked.connect(self._toggle_focus_mode)
        self.focus_toggle_btn.setMinimumHeight(30)
        self.focus_toggle_btn.setStyleSheet(_COMPACT_BTN)
        tool_grid.addWidget(self.focus_toggle_btn, 1, 1)

        # Tools: usage insights + file finder (open as separate windows).
        self.insights_btn = HoverButton("📊 APP INSIGHTS")
        self.insights_btn.clicked.connect(self._open_insights_window)
        self.insights_btn.setMinimumHeight(30)
        self.insights_btn.setStyleSheet(_COMPACT_BTN)
        tool_grid.addWidget(self.insights_btn, 2, 0)
        self.finder_btn = HoverButton("🔎 FILE FINDER")
        self.finder_btn.clicked.connect(self._open_finder_window)
        self.finder_btn.setMinimumHeight(30)
        self.finder_btn.setStyleSheet(_COMPACT_BTN)
        tool_grid.addWidget(self.finder_btn, 2, 1)

        mode_layout.addLayout(tool_grid)

        self._mode_panel = mode_panel
        layout.addWidget(mode_panel)

        # Jarvis left panel: replaces the MODE panel while Jarvis is switched on.
        jv_panel = glass_panel(accent="gold")
        jv_layout = QVBoxLayout(jv_panel)
        jv_title = QLabel("JARVIS SYSTEM MONITOR")
        jv_title.setObjectName("SectionTitle")
        jv_layout.addWidget(jv_title)
        self._sysmon = SystemMonitorPanel()
        self._sysmon.warning.connect(lambda msg: self._deliver_reply(f"Warning. {msg}"))
        jv_layout.addWidget(self._sysmon)
        jv_panel.setVisible(False)
        self._jarvis_left = jv_panel
        layout.addWidget(jv_panel)
        layout.addStretch(1)
        return col

    def _build_center_column(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignTop)

        core_panel = glass_panel()
        core_layout = QVBoxLayout(core_panel)
        core_layout.setAlignment(Qt.AlignCenter)

        self.jarvis_switch_btn = HoverButton("⚡ SWITCH TO JARVIS")
        self.jarvis_switch_btn.clicked.connect(self._toggle_jarvis)
        core_layout.addWidget(self.jarvis_switch_btn, alignment=Qt.AlignCenter)

        self.ai_core = AICoreWidget()
        core_layout.addWidget(self.ai_core, alignment=Qt.AlignCenter)

        self.core_caption = QLabel(AIState.IDLE.label)
        self.core_caption.setObjectName("StateLabel")
        self.core_caption.setAlignment(Qt.AlignCenter)
        core_layout.addWidget(self.core_caption)

        layout.addWidget(core_panel, 3)

        # Conversation panel
        convo_panel = glass_panel()
        convo_layout = QVBoxLayout(convo_panel)
        convo_title = QLabel("CONVERSATION")
        convo_title.setObjectName("SectionTitle")
        convo_layout.addWidget(convo_title)

        self.conversation_view = QTextEdit()
        self.conversation_view.setObjectName("ConversationPanel")
        self.conversation_view.setReadOnly(True)
        convo_layout.addWidget(self.conversation_view)

        input_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setObjectName("CommandInput")
        self.command_input.setPlaceholderText('Type a command, or say "Hey EV…"')
        self.command_input.returnPressed.connect(self._on_send_clicked)
        input_row.addWidget(self.command_input, 1)

        stop_btn = HoverButton("STOP")
        stop_btn.clicked.connect(self._on_stop_clicked)
        input_row.addWidget(stop_btn)

        send_btn = HoverButton("SEND")
        send_btn.setObjectName("SendButton")
        send_btn.clicked.connect(self._on_send_clicked)
        input_row.addWidget(send_btn)
        self.send_btn = send_btn

        # Image help: attach a picture / screenshot and ask about it.
        attach_btn = HoverButton("📎")
        attach_btn.setToolTip("Ask about an image (or drag one into this window)")
        attach_menu = QMenu(attach_btn)
        attach_menu.addAction("Choose an image…").triggered.connect(self._attach_image_from_file)
        attach_menu.addAction("Paste image from clipboard").triggered.connect(self._attach_image_from_clipboard)
        attach_btn.setMenu(attach_menu)
        input_row.insertWidget(input_row.indexOf(self.command_input), attach_btn)
        self.attach_btn = attach_btn
        self._busy_disable_widgets += [self.command_input, send_btn, attach_btn]

        convo_layout.addLayout(input_row)
        layout.addWidget(convo_panel, 4)

        return col

    def _build_right_column(self) -> QWidget:
        col = QWidget()
        layout = QVBoxLayout(col)
        layout.setSpacing(14)

        panel = glass_panel(accent="blue")
        p_layout = QVBoxLayout(panel)
        title = QLabel("QUICK ACTIONS")
        title.setObjectName("SectionTitle")
        p_layout.addWidget(title)

        # Note: there's no "View Memory" button — the feature is still fully
        # there, just reached by typing/saying "view memory" (see
        # handle_user_input's _MEMORY_VIEW_PHRASES check) rather than a
        # dedicated quick-action button.
        quick_actions = [
            ("Open YouTube", "open youtube"),
            ("Search the Web", "search the web for "),
            ("System Info", "what is the cpu usage"),
            ("Clear Conversation", "__clear__"),
        ]
        for label, command in quick_actions:
            btn = HoverButton(label.upper())
            btn.clicked.connect(lambda _, c=command: self._run_quick_action(c))
            p_layout.addWidget(btn)
            # __clear__ doesn't touch the AI brain, so it's fine to use
            # anytime; anything else goes through handle_user_input and
            # must be blocked while a request is already in flight.
            if command != "__clear__":
                self._busy_disable_widgets.append(btn)

        p_layout.addStretch(1)
        self._quick_panel = panel
        layout.addWidget(panel, 1)

        # Jarvis right panel: replaces QUICK ACTIONS while Jarvis is switched on.
        jr_panel = glass_panel(accent="gold")
        jr_layout = QVBoxLayout(jr_panel)
        jr_title = QLabel("JARVIS CHECKS")
        jr_title.setObjectName("SectionTitle")
        jr_layout.addWidget(jr_title)
        for label, command in (
            ("Full Status Report", "give me a full status report"),
            ("Top Processes", "what is using the most CPU and memory right now"),
            ("Disk Space", "check my disk space"),
            ("Battery Check", "check my battery"),
            ("Network Check", "check my network and internet"),
            ("Health Check", "run a system health check"),
        ):
            jb = HoverButton(label.upper())
            jb.clicked.connect(lambda _=False, c=command: self._run_quick_action(c))
            jr_layout.addWidget(jb)
            if command != "__clear__":
                self._busy_disable_widgets.append(jb)
        jr_layout.addStretch(1)
        jr_panel.setVisible(False)
        self._jarvis_right = jr_panel
        layout.addWidget(jr_panel, 1)

        # Build-info panel removed from here — that info (version,
        # platform, provider) now lives in Settings (gear icon) instead
        # of taking up permanent space on the dashboard.

        return col

    # ------------------------------------------------------------------
    # Behavior
    # ------------------------------------------------------------------
    def _on_send_clicked(self):
        text = self.command_input.text().strip()
        if not text:
            return
        self.command_input.clear()
        self.handle_user_input(text)

    def _run_quick_action(self, command: str):
        if command == "__clear__":
            self.conversation_view.clear()
            return
        self.handle_user_input(command)

    def _view_memory(self):
        """Shows stored memory directly from the database — no AI call
        needed, so you can always check what's stored even without an
        API key configured. This is the 'view stored memory' UI control
        from the project spec."""
        store = memory_tools.get_store()
        memories = store.recall()["memories"]
        frequent = store.frequent_apps()["frequent_apps"]

        lines = []
        if memories:
            lines.append("<b>Stored memories:</b>")
            for m in memories:
                lines.append(
                    f"&nbsp;&nbsp;[{html.escape(m['category'])}] "
                    f"{html.escape(m['key'])}: {html.escape(m['value'])}"
                )
        else:
            lines.append("No stored memories yet.")

        if frequent:
            lines.append("<b>Frequently used apps:</b>")
            for f in frequent:
                lines.append(f"&nbsp;&nbsp;{html.escape(f['app_name'])} (opened {f['open_count']}x)")

        self._append_conversation("EV", "<br>".join(lines))

    def _on_stop_clicked(self):
        """Interrupt whatever EV is currently doing — speaking or listening
        for a command — and return to IDLE. This is the 'ability to
        interrupt/cancel a response' from the project spec."""
        if self._speech_worker is not None:
            self._speech_worker.stop_speaking()
        if self._state in (AIState.LISTENING, AIState.THINKING, AIState.EXECUTING, AIState.SPEAKING):
            self._apply_state(AIState.IDLE)

    # Phrases that show stored memory directly (no AI call needed) rather
    # than going to the brain — this is how the feature stays reachable
    # now that there's no dedicated "View Memory" button.
    _MEMORY_VIEW_PHRASES = (
        "view memory", "show memory", "show my memory",
        "what do you remember", "what's in memory", "whats in memory",
    )

    def handle_user_input(self, text: str):
        """LISTENING -> THINKING -> (real AI call) -> SPEAKING -> IDLE.

        Guarded against re-entry: if EV is already mid-request, a second
        call here is ignored rather than starting a second brain call on
        top of the first. Two requests running at once shared one
        conversation history and produced merged/out-of-order replies —
        this closes that gap. The UI additionally disables Send/quick
        actions while busy (see _apply_state) as a second line of defense.
        """
        if self._state != AIState.IDLE:
            return
        self._append_conversation("You", text)
        self._recent_commands.append(text)
        self._recent_commands = self._recent_commands[-5:]
        if self._hud_overlay is not None:
            self._hud_overlay.set_recent_commands(self._recent_commands)

        if text.strip().lower() in self._MEMORY_VIEW_PHRASES:
            self._view_memory()
            return

        self._apply_state(AIState.LISTENING)
        self._run_brain(text)

    def _try_offline(self, text: str, fallback: bool) -> bool:
        """Answer with the built-in command handler (core/offline.py).
        Returns True if it handled the request."""
        if self._offline is None:
            return False
        if getattr(self, "_jarvis_on", False) and not fallback:
            return False   # Jarvis only monitors the system; EV's offline commands stay off
        try:
            reply = self._offline.handle(text, fallback=fallback)
        except Exception as e:
            print(f"[EV AI] Offline handler error: {e}")
            return False
        if not reply:
            return False
        self._deliver_reply(reply if not fallback else f"{reply} (offline mode)")
        return True

    def _run_brain(self, text: str):
        self._apply_state(AIState.THINKING)
        self._last_text = text

        # Jarvis Pro: expand custom voice/text macros before offline/AI.
        try:
            from tools import macros as _macro_tools
            hit = {} if self._jarvis_on else _macro_tools.match_macro(text)
            if hit.get("matched"):
                text = hit["action"]
                self._last_text = text
                self._append_conversation("EV", f"(macro: {hit['trigger']})")
        except Exception as e:
            print(f"[EV AI] Macro match error: {e}")

        # Optional speed path: everyday commands without an AI round-trip.
        if user_prefs.get("offline_first") and self._try_offline(text, fallback=False):
            return

        if not AI_AVAILABLE:
            self._deliver_reply(
                "My AI brain isn't installed yet — run pip install -r requirements.txt "
                "to add it."
            )
            return
        if not self._brain.is_configured:
            if self._try_offline(text, fallback=True):
                return
            if self._brain.init_error:
                # Missing package / unsupported provider — a different
                # problem than "no key set", and worth saying so plainly.
                self._deliver_reply(f"My AI brain can't start: {self._brain.init_error}")
            else:
                self._deliver_reply(
                    "I don't have an AI_API_KEY set yet — add one to your .env file and "
                    "restart me to turn my AI brain on."
                )
            return

        self._phone_call_sent = False
        self._brain_worker = BrainWorker(self._brain, text, parent=self)
        self._brain_worker.reply_ready.connect(self._on_brain_reply)
        self._brain_worker.brain_error.connect(self._on_brain_error)
        self._brain_worker.start()

    def _on_brain_reply(self, reply: str):
        self._deliver_reply(reply)

    def _on_brain_error(self, message: str):
        if "reach the AI service" in message and self._try_offline(self._last_text, fallback=True):
            return   # no internet: the basics still work
        self._apply_state(AIState.ERROR)
        self._append_conversation("EV", f"(error) {message}")
        QTimer.singleShot(1800, lambda: self._apply_state(AIState.IDLE))

    def _deliver_reply(self, reply: str):
        self._apply_state(AIState.SPEAKING)
        self._append_conversation("EV", reply)
        if self._hud_overlay is not None:
            self._hud_overlay.set_last_reply(reply)
        self._speak(reply)

    # ------------------------------------------------------------------
    # Voice: listening (mic -> wake word -> command)
    # ------------------------------------------------------------------
    def _toggle_voice(self):
        if not VOICE_AVAILABLE:
            return
        if self._listener_thread is not None and self._listener_thread.isRunning():
            self.mic_toggle_btn.setText("🎤 START VOICE")
            self.mic_toggle_btn.setChecked(False)
            self._listener_thread.stop()
        else:
            self._stop_clap_detector()  # only one thread should hold the mic at a time
            self.mic_toggle_btn.setText("🎤 STOP VOICE")
            self.mic_toggle_btn.setChecked(True)
            self._listener_thread = VoiceListenerThread(settings.WAKE_WORD, parent=self)
            self._listener_thread.heard_text.connect(self._on_heard_text)
            self._listener_thread.wake_word_detected.connect(self._on_wake_word_detected)
            self._listener_thread.mic_error.connect(self._on_mic_error)
            self._listener_thread.listening_state_changed.connect(self._on_listening_state_changed)
            self._listener_thread.finished.connect(self._on_listener_finished)
            self._listener_thread.start()
        if self._hud_overlay is not None:
            self._hud_overlay.set_mic_active(
                self._listener_thread is not None and self._listener_thread.isRunning()
            )

    def _on_heard_text(self, text: str):
        # Show what EV heard, even if it wasn't the wake word — this is the
        # "show what EV heard on the UI" requirement, kept out of the main
        # conversation log so ambient chatter doesn't spam it.
        shown = text if len(text) <= 60 else text[:57] + "…"
        self.last_heard_label.setText(f"LAST HEARD: {shown}")

    def _on_wake_word_detected(self, command: str):
        if self._state != AIState.IDLE:
            return  # ignore new wake-ups while EV is already busy
        if command:
            self.handle_user_input(command)
        else:
            # Just "Hey EV" with no command attached — acknowledge and wait.
            self._append_conversation("EV", "Yes?")
            self._apply_state(AIState.SPEAKING)
            self._speak("Yes?")

    def _on_mic_error(self, message: str):
        self.mic_status_label.setText("MIC: ERROR")
        self.last_heard_label.setText(f"LAST HEARD: (error) {message}")
        self.mic_toggle_btn.setText("🎤 START VOICE")
        self.mic_toggle_btn.setChecked(False)
        self._start_clap_detector()  # hand the mic back to clap listening

    def _on_listening_state_changed(self, is_listening: bool):
        if is_listening:
            self.mic_status_label.setText("MIC: LISTENING")
        elif self.mic_status_label.text() != "MIC: ERROR":
            self.mic_status_label.setText("MIC: OFF")

    def _on_listener_finished(self):
        self.mic_toggle_btn.setText("🎤 START VOICE")
        self.mic_toggle_btn.setChecked(False)
        self._start_clap_detector()  # hand the mic back to clap listening

    # ------------------------------------------------------------------
    # Voice: clap-to-activate (lightweight, always-on when voice mode is off)
    # ------------------------------------------------------------------
    def _start_clap_detector(self):
        if not VOICE_AVAILABLE:
            return
        if self._listener_thread is not None and self._listener_thread.isRunning():
            return  # wake-word listener already has the mic
        if self._clap_detector is not None and self._clap_detector.isRunning():
            return  # already running
        self._clap_detector = ClapDetectorThread(parent=self)
        self._clap_detector.clap_detected.connect(self._on_clap_detected)
        self._clap_detector.mic_error.connect(self._on_clap_mic_error)
        self._clap_detector.start()

    def _stop_clap_detector(self):
        if self._clap_detector is not None and self._clap_detector.isRunning():
            self._clap_detector.stop()
            self._clap_detector.wait(500)

    def _on_clap_detected(self):
        if self._listener_thread is not None and self._listener_thread.isRunning():
            return  # already listening
        self._append_conversation("EV", "(clap detected) Voice mode on.")
        self._toggle_voice()

    def _on_clap_mic_error(self, message: str):
        # Clap detection is a convenience feature, not core functionality —
        # log it quietly rather than raising an ERROR state over it.
        print(f"[EV AI] Clap detector unavailable: {message}")

    # ------------------------------------------------------------------
    # Voice: speaking (text -> TTS)
    # ------------------------------------------------------------------
    def _speak(self, text: str):
        if not VOICE_AVAILABLE or not user_prefs.get("speak_replies"):
            # No TTS available — fall back to a short pause so the SPEAKING
            # state is still visible, then return to IDLE.
            QTimer.singleShot(1000, lambda: self._apply_state(AIState.IDLE))
            return

        # Let a previous utterance finish naturally rather than overlapping
        # two TTS engines; interrupting is what the STOP button is for.
        if self._speech_worker is not None and self._speech_worker.isRunning():
            self._speech_worker.stop_speaking()
            self._speech_worker.wait(500)

        self._speech_worker = SpeechWorker(text, parent=self)
        self._speech_worker.finished_speaking.connect(self._on_speech_finished)
        self._speech_worker.start()

    def _on_speech_finished(self):
        if self._state == AIState.SPEAKING:
            self._apply_state(AIState.IDLE)

    def _on_reminder_fired(self, message: str):
        """A tools/reminders.py timer went off — announce it. Reuses the
        same _speak() path as a normal reply, so it interrupts cleanly
        even if EV happens to be speaking something else at that moment."""
        self._append_conversation("EV", f"⏰ {message}")
        self._apply_state(AIState.SPEAKING)
        self._speak(message)

    def _check_scheduled_tasks(self):
        """Stage 8: polled every 20s — fires any recurring scheduled task
        (see core/automation.py) whose time has come. Runs its paired
        tool call (if any) through the same ToolRouter the AI brain uses,
        then announces the message the same way a one-off reminder does."""
        from datetime import datetime
        from tools import automation as automation_tools

        store = automation_tools.get_store()
        now = datetime.now()
        due = store.due_tasks(now)
        for task in due:
            store.mark_fired(task["id"], now.strftime("%Y-%m-%d"))
            if task["tool_name"] and self._tool_router is not None:
                try:
                    self._tool_router.execute(task["tool_name"], task["tool_args"])
                except Exception as e:
                    print(f"[EV AI] Scheduled task {task['id']} tool call failed: {e}")
            self._on_reminder_fired(task["message"])

    # ------------------------------------------------------------------
    # Modes
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Jarvis switch: gold core, different panels, Jarvis personality prompt
    # ------------------------------------------------------------------
    def _toggle_jarvis(self):
        self._apply_jarvis_ui(not self._jarvis_on, announce=True)

    def _apply_jarvis_ui(self, on: bool, announce: bool = False):
        self._jarvis_on = on
        user_prefs.set_value("jarvis_ui", on)
        self.ai_core.set_jarvis(on)
        from ui.jarvis_style import JARVIS_QSS
        self._central.setStyleSheet(JARVIS_QSS if on else "")
        self._logo_label.setText("J.A.R.V.I.S" if on else settings.APP_NAME)
        self._mode_panel.setVisible(not on)
        self._jarvis_left.setVisible(on)
        self._quick_panel.setVisible(not on)
        self._jarvis_right.setVisible(on)
        if on:
            self._sysmon.start()
        else:
            self._sysmon.stop()
        if on:
            self._pre_jarvis_mode = self._current_mode if self._current_mode not in (None, Mode.JARVIS) else Mode.NORMAL
            self.jarvis_switch_btn.setText("⚡ SWITCH BACK TO EV")
            self.jarvis_switch_btn.setStyleSheet(
                "QPushButton { background: rgba(255,196,0,40); border: 1px solid #FFC400; color: #FFC400; "
                "padding: 6px 16px; border-radius: 6px; font-weight: 600; }"
            )
            if self._brain is not None:
                self._brain.set_mode(Mode.JARVIS)
            self._current_mode = Mode.JARVIS if AI_AVAILABLE else None
        else:
            self.jarvis_switch_btn.setText("⚡ SWITCH TO JARVIS")
            self.jarvis_switch_btn.setStyleSheet("")
            back = getattr(self, "_pre_jarvis_mode", None) or Mode.NORMAL
            if self._brain is not None:
                self._brain.set_mode(back)
            self._current_mode = back if AI_AVAILABLE else None
            for m, btn in self._mode_buttons.items():
                btn.setChecked(m == back)
        if announce:
            self._deliver_reply("Switched to Jarvis." if on else "Switched back to EV.")
        self._sync_corner_ui()

    def _set_mode(self, mode: Mode):
        if self._brain is not None:
            self._brain.set_mode(mode)
        for m, btn in self._mode_buttons.items():
            btn.setChecked(m == mode)
        self._current_mode = mode
        self._append_conversation("EV", f"({mode.label} mode on)")
        self._sync_corner_ui()

    # ------------------------------------------------------------------
    # Observation mode: periodic screenshot -> vision call -> speak if
    # there's something worth saying. OFF by default; the person must
    # explicitly turn it on. See core/brain.py's OBSERVE_PROMPT for what
    # counts as "worth mentioning".
    # ------------------------------------------------------------------
    OBSERVE_INTERVAL_MS = 20_000

    def _toggle_observation(self):
        if not AI_AVAILABLE:
            return
        if self._observing:
            self._stop_observation()
        else:
            self._start_observation()

    def _start_observation(self):
        self._observing = True
        self._last_screen_hash = None
        self.observe_toggle_btn.setText("👁 OBSERVE: ON")
        self.observe_toggle_btn.setChecked(True)
        self._append_conversation(
            "EV", "(Observation mode on — I'll glance at your screen occasionally. "
                  "Screenshots are sent to the AI service while this is on.)"
        )
        self._observe_timer = QTimer(self)
        self._observe_timer.timeout.connect(self._maybe_observe)
        self._observe_timer.start(int(user_prefs.get("observe_interval_s")) * 1000)
        self._maybe_observe()  # don't wait a full interval for the first check
        self._sync_corner_ui()

    def _stop_observation(self):
        self._observing = False
        self.observe_toggle_btn.setText("👁 OBSERVE: OFF")
        self.observe_toggle_btn.setChecked(False)
        if self._observe_timer is not None:
            self._observe_timer.stop()
            self._observe_timer = None
        self._sync_corner_ui()

    # ------------------------------------------------------------------
    # Corner UI: replace the full dashboard with a compact overlay
    # whenever certain modes are active.
    #   - Automatic, Serious, Study, or Observation mode -> full-screen
    #     transparent HUD overlay (the small floating ring was retired —
    #     every corner-UI-triggering mode now uses the HUD).
    # Exactly one of {HUD, full dashboard} is visible at any time.
    # ------------------------------------------------------------------
    def _should_use_hud(self) -> bool:
        mode_wants_it = self._current_mode is not None and self._current_mode.uses_hud_overlay
        return mode_wants_it or self._observing

    def _sync_corner_ui(self) -> None:
        want_hud = self._should_use_hud()

        if want_hud:
            if self._hud_overlay is None:
                self._hud_overlay = HUDOverlayWidget()
                self._hud_overlay.text_submitted.connect(self.handle_user_input)
                self._hud_overlay.restore_requested.connect(self._exit_corner_ui)
                self._hud_overlay.quick_action_requested.connect(self._run_quick_action)
                self._hud_overlay.mic_toggle_requested.connect(self._toggle_voice)
                self._hud_overlay.stop_requested.connect(self._on_stop_clicked)
                self._hud_overlay.video_toggle_requested.connect(self._toggle_video_mode)
            self._hud_overlay.set_state(self._state)
            mode_is_hud_mode = self._current_mode and self._current_mode.uses_hud_overlay
            self._hud_overlay.set_mode_label(
                f"{self._current_mode.label} MODE" if mode_is_hud_mode else "OBSERVING"
            )
            self._hud_overlay.set_mic_active(
                self._listener_thread is not None and self._listener_thread.isRunning()
            )
            self._hud_overlay.set_video_active(self._video_mode_on)
            self._hud_overlay.show_overlay()
            self.hide()
        else:
            if self._hud_overlay is not None:
                self._hud_overlay.hide_overlay()
            self.show()
            self.raise_()
            self.activateWindow()

    def _exit_corner_ui(self) -> None:
        """The person asked for the full dashboard back (clicked a
        restore button or double-clicked the ring). Drops back to Normal
        mode and turns Observation off, rather than leaving corner-UI
        state active behind a now-visible window."""
        if self._observing:
            self._stop_observation()
        if AI_AVAILABLE and Mode is not None:
            self._set_mode(Mode.NORMAL)
        else:
            self._sync_corner_ui()

    # ------------------------------------------------------------------
    # Image help: explain / read / debug an image the user chooses to share.
    # ------------------------------------------------------------------
    _IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
    _MAX_IMAGE_SIDE = 1600

    def _attach_image_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose an image", "", self._IMAGE_FILTER)
        if path:
            self._ask_about_image(QImage(path), path.replace("\\", "/").split("/")[-1])

    def _attach_image_from_clipboard(self):
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            self._append_conversation("EV", "(There's no image on the clipboard — take a screenshot "
                                            "with Win+Shift+S, then try again.)")
            return
        self._ask_about_image(image, "clipboard image")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")):
                    self._ask_about_image(QImage(path), path.replace("\\", "/").split("/")[-1])
                    return
        elif mime.hasImage():
            self._ask_about_image(QImage(mime.imageData()), "dropped image")

    def _ask_about_image(self, image: QImage, label: str):
        if self._state != AIState.IDLE:
            return
        if image.isNull():
            self._append_conversation("EV", "(I couldn't read that image file.)")
            return
        if not AI_AVAILABLE or not self._brain.is_configured:
            self._append_conversation("EV", "(Image help needs the AI — add an API key in Settings first.)")
            return
        longest = max(image.width(), image.height())
        if longest > self._MAX_IMAGE_SIDE:
            image = image.scaled(self._MAX_IMAGE_SIDE, self._MAX_IMAGE_SIDE,
                                 Qt.KeepAspectRatio, Qt.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.convertToFormat(QImage.Format_RGB32).save(buffer, "JPEG", 88)
        data = bytes(buffer.data())
        buffer.close()

        question = self.command_input.text().strip() or "Explain what this shows, and read out any text in it."
        self.command_input.clear()
        self._append_conversation("You", f"📎 {label} — {question}")
        self._last_text = question
        self._apply_state(AIState.THINKING)
        self._image_worker = ImageWorker(self._brain, data, "image/jpeg", question, label, parent=self)
        self._image_worker.reply_ready.connect(self._on_brain_reply)
        self._image_worker.brain_error.connect(self._on_brain_error)
        self._image_worker.start()

    def _capture_screen_png(self) -> bytes | None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        pixmap = screen.grabWindow(0)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        data = bytes(buffer.data())
        buffer.close()
        return data

    def _maybe_observe(self):
        # Don't interrupt an active conversation, and don't pile up a new
        # capture while a previous one is still being analyzed.
        if not self._observing or self._state != AIState.IDLE:
            print("[EV AI] Observation: skipped (busy or off).")
            return
        if self._vision_worker is not None and self._vision_worker.isRunning():
            print("[EV AI] Observation: skipped (previous check still running).")
            return

        try:
            image_bytes = self._capture_screen_png()
        except Exception as e:
            print(f"[EV AI] Observation: screen capture failed ({e}).")
            return  # screen capture is best-effort; silently skip a failed attempt
        if not image_bytes:
            print("[EV AI] Observation: screen capture returned nothing.")
            return

        screen_hash = hashlib.sha256(image_bytes).hexdigest()
        if screen_hash == self._last_screen_hash:
            print("[EV AI] Observation: screen unchanged since last check, skipping API call.")
            return  # unchanged since last check — skip the API call entirely
        self._last_screen_hash = screen_hash

        print("[EV AI] Observation: screen changed, asking the AI to take a look...")
        self._vision_worker = VisionWorker(self._brain, image_bytes, parent=self)
        self._vision_worker.comment_ready.connect(self._on_observation_comment)
        self._vision_worker.nothing_found.connect(self._on_observation_nothing)
        self._vision_worker.vision_error.connect(self._on_observation_error)
        self._vision_worker.start()

    def _on_observation_comment(self, comment: str):
        print(f"[EV AI] Observation: AI had something to say: {comment!r}")
        if self._state != AIState.IDLE:
            return  # user started doing something else while this was in flight
        self._append_conversation("EV", f"👁 {comment}")
        self._apply_state(AIState.SPEAKING)
        self._speak(comment)

    def _on_observation_nothing(self):
        print("[EV AI] Observation: nothing worth mentioning this time.")

    def _on_observation_error(self, message: str):
        # A failed background glance shouldn't interrupt the user with an
        # ERROR state — just log it and try again next interval.
        print(f"[EV AI] Observation mode error: {message}")

    # ------------------------------------------------------------------
    # Video mode: continuous webcam hand-gesture control (pinch to zoom).
    # OFF by default; the person must explicitly turn it on. Unlike
    # Observation mode, there's no periodic timer — GestureWorker holds
    # the camera open and runs its own loop for as long as it's on.
    # ------------------------------------------------------------------
    def _toggle_video_mode(self):
        if not GESTURE_AVAILABLE:
            return
        if self._video_mode_on:
            self._stop_video_mode()
        else:
            self._start_video_mode()

    def _start_video_mode(self):
        self._video_mode_on = True
        self.video_toggle_btn.setText("🎥 VIDEO: ON")
        self.video_toggle_btn.setChecked(True)
        if self._hud_overlay is not None:
            self._hud_overlay.set_video_active(True)
        self._append_conversation(
            "EV", "(Video mode on. Two hands together/apart = zoom · swipe one hand = next/previous tab · "
                  "swipe both hands = switch desktop · hand up/down = volume · hold 1/2/3 fingers = Win+1/2/3 · "
                  "hold an open palm = pause, hold a fist = resume. See Settings → Gesture control. "
                  "The webcam stays open while this is on.)"
        )
        self._video_view = VideoViewWindow()
        self._video_view.closed.connect(self._on_video_view_closed)
        self._video_view.show_centered()
        if not user_prefs.get("seen_gesture_guide"):
            user_prefs.set_value("seen_gesture_guide", True)
            from ui.gesture_guide import GestureGuide
            self._gesture_guide = GestureGuide(self)
            self._gesture_guide.show()
        self._gesture_worker = GestureWorker(parent=self)
        self._gesture_worker.status.connect(self._on_gesture_status)
        self._gesture_worker.error.connect(self._on_gesture_error)
        self._gesture_worker.frame_ready.connect(self._on_gesture_frame)
        self._gesture_worker.start()

    def release_camera(self) -> bool:
        """Free the webcam for other apps. Returns True if EV AI was using it."""
        was_on = bool(self._video_mode_on or self._gesture_worker is not None)
        if was_on:
            self._stop_video_mode()
        return was_on

    def _on_video_view_closed(self):
        # The person closed the camera window: that means "turn Video mode off".
        self._video_view = None
        if self._video_mode_on:
            self._stop_video_mode()

    def _stop_video_mode(self):
        self._video_mode_on = False
        if self._video_view is not None:
            view, self._video_view = self._video_view, None
            try:
                view.closed.disconnect(self._on_video_view_closed)
            except (TypeError, RuntimeError):
                pass
            view.close()
        self.video_toggle_btn.setText("🎥 VIDEO: OFF")
        self.video_toggle_btn.setChecked(False)
        if self._hud_overlay is not None:
            self._hud_overlay.set_video_active(False)
        if self._gesture_worker is not None:
            self._gesture_worker.stop()
            self._gesture_worker.wait(2000)
            self._gesture_worker = None

    # ------------------------------------------------------------------
    # Song mode: a floating music remote (ui/song_panel.py).
    # ------------------------------------------------------------------
    def _toggle_song_mode(self):
        if self._song_panel is not None:
            self._song_panel.close()
            return
        self._song_panel = SongPanel()
        self._song_panel.closed.connect(self._on_song_panel_closed)
        self._song_panel.show_at_corner()
        self.song_toggle_btn.setText("🎵 SONG: ON")
        self.song_toggle_btn.setChecked(True)

    def _on_song_panel_closed(self):
        self._song_panel = None
        self.song_toggle_btn.setText("🎵 SONG: OFF")
        self.song_toggle_btn.setChecked(False)

    def _on_gesture_status(self, text: str):
        print(f"[EV AI] Video mode: {text}")
        if self._video_view is not None:
            self._video_view.set_status(text)
        if self._hud_overlay is not None:
            self._hud_overlay.set_video_status(text)

    def _on_gesture_frame(self, data: dict):
        # Live preview for the HUD's left-side video panel — only matters
        # while the HUD is actually up, but cheap to no-op otherwise.
        if self._video_view is not None:
            self._video_view.set_frame(data)
        if self._hud_overlay is not None:
            self._hud_overlay.set_video_frame(data)

    def _on_gesture_error(self, message: str):
        print(f"[EV AI] Video mode error: {message}")
        self._append_conversation("EV", f"(Video mode couldn't start — {message})")
        self._stop_video_mode()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Connected device: phone the user's mobile if the computer goes down
    # while EV is still working on a request.
    # ------------------------------------------------------------------
    def _hook_shutdown_call(self) -> None:
        try:
            app = QApplication.instance()
            if app is None:
                return
            app.aboutToQuit.connect(self._call_phone_if_working)
            if hasattr(app, "commitDataRequest"):
                app.commitDataRequest.connect(lambda *_: self._call_phone_if_working())
        except Exception as e:
            print(f"[EV AI] Shutdown call hook failed: {e}")

    def _call_phone_if_working(self) -> None:
        try:
            if self._phone_call_sent:
                return
            working = self._brain_worker is not None and self._brain_worker.isRunning()
            if not working:
                return
            self._phone_call_sent = True
            from core import devices
            ok, msg = devices.call_for_shutdown(self._last_text)
            print(f"[EV AI] Shutdown phone call: {msg}")
        except Exception as e:
            print(f"[EV AI] Shutdown phone call error: {e}")

    def closeEvent(self, event):
        if self._tray.should_hide_on_close():
            event.ignore()
            # Hidden in the tray must not keep the webcam locked (Video mode
            # holds it open) — otherwise the Camera app says "another app is
            # using the camera".
            self.release_camera()
            self.hide()
            self._tray.notify_hidden()
            return
        self._call_phone_if_working()
        self._hotkey.disable()
        self._focus.stop()
        self._usage.stop()
        if self._song_panel is not None:
            self._song_panel.close()
        self._stop_observation()
        self._stop_video_mode()
        self._stop_clap_detector()
        if self._hud_overlay is not None:
            self._hud_overlay.close()
        if self._listener_thread is not None and self._listener_thread.isRunning():
            self._listener_thread.stop()
            self._listener_thread.wait(2000)
        if self._speech_worker is not None and self._speech_worker.isRunning():
            self._speech_worker.stop_speaking()
            self._speech_worker.wait(500)
        self._drain_threads()
        super().closeEvent(event)

    def _drain_threads(self) -> None:
        """Last step of quitting: make sure no worker thread is still running
        when Qt tears everything down (that is what prints "QThread: Destroyed
        while thread is still running"). Each gets a polite stop request and a
        short wait; a thread that still won't end is terminated, because the
        app is exiting anyway."""
        from PySide6.QtCore import QThread
        for thread in self.findChildren(QThread):
            if not thread.isRunning():
                continue
            for stopper in ("stop", "stop_speaking"):
                fn = getattr(thread, stopper, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
                    break
            thread.quit()
            if not thread.wait(1500):
                thread.terminate()
                thread.wait(500)

    # ------------------------------------------------------------------
    # State + metrics
    # ------------------------------------------------------------------
    def _apply_state(self, state: AIState):
        self._state = state
        self.ai_core.set_state(state)
        self.state_label.setText(state.label)
        self.core_caption.setText(state.label)
        if self._hud_overlay is not None:
            self._hud_overlay.set_state(state)
        busy = state != AIState.IDLE
        for widget in self._busy_disable_widgets:
            widget.setEnabled(not busy)

    def _append_conversation(self, speaker: str, text: str):
        self.conversation_view.append(f"<b>{speaker}:</b> {text}")

    def _refresh_metrics(self):
        now = datetime.datetime.now()
        self.time_value.setText(now.strftime("%H:%M:%S"))
        # DD-MM-YY + weekday, e.g. "12-10-26 Saturday".
        self.date_value.setText(now.strftime("%d-%m-%y %A"))

        try:
            cpu_text = f"{psutil.cpu_percent(interval=None):.0f}%"
            ram_text = f"{psutil.virtual_memory().percent:.0f}%"
            self.cpu_value.setText(cpu_text)
            self.ram_value.setText(ram_text)
        except Exception:
            # Never let a metrics failure crash the UI.
            cpu_text, ram_text = "N/A", "N/A"
            self.cpu_value.setText(cpu_text)
            self.ram_value.setText(ram_text)
        if self._hud_overlay is not None:
            self._hud_overlay.set_metrics(cpu_text, ram_text)

        # Simple internet check placeholder — a real check is added in a
        # later stage (it will avoid blocking the UI thread).
        self.internet_status_label.setText("INTERNET: (checked at startup)")
