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
import time
from pathlib import Path
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
    remote_mode = Signal(str)         # the phone asked for a mode (from a worker thread)
    bridge_reply = Signal(str)        # answer to a voice question about the Chrome page (from a worker thread)
    usb_inserted = Signal(str, str)   # drive, label (from the USB watcher thread)
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
        self._game_on = False
        self._style_char = None           # "friday", "tars" or "gideon" while one of those characters is on
        self._karen_on = False
        self._ultron_on = False
        self._pre_jarvis_mode = None
        self._pre_ultron_mode = None
        self._phone_call_sent = False
        self._build_ui()
        self._hook_shutdown_call()
        try:
            from PySide6.QtWidgets import QMessageBox
            from config import APP_ROOT
            from core import updater as _upd
            from app_version import VERSION as _ver
            import threading as _th
            _th.Thread(target=_upd.cleanup_leftovers, args=(APP_ROOT,), daemon=True).start()
            _note = _upd.failed_update_notice(APP_ROOT, _ver)
            if _note:
                QTimer.singleShot(4000, lambda: QMessageBox.warning(self, "Update did not install", _note))
        except Exception as e:
            print(f"[EV AI] Update check skipped: {e}")
        try:
            from ui.compute_ui import controller
            controller().set_ask(self._remote_ask)
            controller().host.mode_fn = lambda k: (self.remote_mode.emit(k) or f"Done: {k}.")
            controller().start()
        except Exception as e:
            print(f"[EV AI] Compute unavailable: {e}")
        if user_prefs.get("jarvis_ui"):
            QTimer.singleShot(0, lambda: self._apply_jarvis_ui(True, announce=False))
        elif user_prefs.get("ultron_ui"):
            QTimer.singleShot(0, lambda: self._apply_ultron_ui(True, announce=False))
        self._apply_state(AIState.IDLE)

        if not VOICE_AVAILABLE:
            self.mic_status_label.setText("MIC: VOICE DEPS NOT INSTALLED")
            self.mic_toggle_btn.setEnabled(False)
            self.mic_toggle_btn.setToolTip(
                f"Voice features unavailable: {VOICE_IMPORT_ERROR}\n"
                "Run: pip install -r requirements.txt"
            )

        # Live system clock + resource usage, refreshed on a timer.
        self._mode_sync_timer = QTimer(self)
        self._mode_sync_timer.timeout.connect(self._sync_mode_button)
        self._mode_sync_timer.start(400)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._refresh_metrics)
        self._clock_timer.start(settings.UI_REFRESH_MS)
        self._refresh_metrics()

        # Chrome extension bridge (127.0.0.1 only; see core/browser_bridge.py)
        self.bridge_reply.connect(lambda t: self._deliver_reply(t))
        self.remote_mode.connect(self._select_mode)
        if user_prefs.get("chrome_bridge"):
            try:
                from core import browser_bridge
                browser_bridge.create(self._bridge_ask, self.bridge_reply.emit, self._bridge_count).start()
            except Exception as e:
                print(f"[EV AI] Chrome bridge unavailable: {e}")
        self._start_karen()
        QTimer.singleShot(8000, self._cloud_sync)

        # USB drives plugged in to this PC: bring EV forward and announce them.
        self.usb_inserted.connect(self._on_usb_inserted)
        try:
            from core.usb_watch import UsbWatcher
            self._usb_watcher = UsbWatcher(lambda d, l: self.usb_inserted.emit(d, l))
            self._usb_watcher.start()
        except Exception as e:
            print(f"[EV AI] USB watcher unavailable: {e}")

        # Low-battery warning (laptops): speaks once at 20% and again at 10% while unplugged.
        self._battery_warned = 100
        self._battery_timer = QTimer(self)
        self._battery_timer.timeout.connect(self._check_battery)
        self._battery_timer.start(60_000)
        self.ai_core.clicked.connect(self._on_orb_clicked)
        QTimer.singleShot(0, self._refresh_face)

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

        body_layout.addWidget(self._scroll_wrap(self._build_left_column()), 2)
        body_layout.addWidget(self._scroll_wrap(self._build_center_column()), 3)
        self._right_scroll = self._scroll_wrap(self._build_right_column())
        body_layout.addWidget(self._right_scroll, 2)

        root.addWidget(body, 1)
        # The panels of some screens (Ultron, Game, Karen) need more height than a small laptop screen has.
        # Inside a scroll area the window never grows past the screen; a scroll bar appears only when needed.
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

    @staticmethod
    def _scroll_wrap(col: QWidget) -> QWidget:
        """A column that scrolls by itself when the screen is too short, instead of making the whole window taller."""
        from PySide6.QtWidgets import QScrollArea
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setStyleSheet("QScrollArea { background: transparent; border: 0; } "
                         "QScrollArea > QWidget > QWidget { background: transparent; } "
                         "QScrollBar:vertical { width: 6px; background: transparent; } "
                         "QScrollBar::handle:vertical { background: rgba(120,160,200,90); border-radius: 3px; min-height: 30px; } "
                         "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")
        sa.viewport().setAutoFillBackground(False)
        sa.setWidget(col)
        sa.setMinimumHeight(120)
        return sa

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
        dialog.home_layout_changed.connect(self.apply_home_layout)
        dialog.exec()

    # ------------------------------------------------------------------
    # Quick Actions, Focus Mode, personalization, clipboard helpers
    # ------------------------------------------------------------------
    def _open_computer_control(self) -> None:
        """EV's main feature: pair a phone and control this computer from it (same window as Settings > Phone control)."""
        from ui.compute_ui import ComputeDialog
        ComputeDialog(self).exec()

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

    def _remote_ask(self, text: str) -> str:
        """Runs a command sent from the phone (Compute > Ask EV). Called on a background thread,
        only while a remote session you approved is active."""
        try:
            if self._offline is not None:
                reply = self._offline.handle(text, fallback=False)
                if reply:
                    return reply
            if not AI_AVAILABLE or self._tool_router is None:
                return "The AI isn't available on the computer."
            if getattr(self, "_remote_brain", None) is None:
                self._remote_brain = Brain(router=self._tool_router)
            return self._remote_brain.ask(text)
        except Exception as e:
            return f"Sorry, that failed: {e}"

    def _bridge_count(self, site: str, n: int) -> int:
        """The extension counted n short videos (worker thread). EV speaks up every 25."""
        from core import shorts
        today, milestone = shorts.record(site, n)
        if milestone:
            self.bridge_reply.emit(f"That's {today} shorts scrolled today, sir. Perhaps time for a break.")
        return today

    def _bridge_ask(self, question: str, page: dict) -> str:
        """A question about a web page you chose to share from the Chrome extension (worker thread)."""
        if not AI_AVAILABLE:
            return "The AI isn't available on the computer."
        from core.browser_bridge import page_prompt
        if getattr(self, "_page_brain", None) is None:
            self._page_brain = Brain(router=None)
        self._page_brain._history.clear()          # each page question stands alone
        return self._page_brain.ask(page_prompt(question, page))

    def _on_usb_inserted(self, drive: str, label: str) -> None:
        if not user_prefs.get("usb_alert"):
            return
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()
        name = f"{label} ({drive.rstrip(chr(92))})" if label else drive.rstrip(chr(92))
        self._deliver_reply(f"USB drive {name} detected.")

    def _check_battery(self) -> None:
        if not user_prefs.get("battery_alerts"):
            return
        try:
            import psutil
            bat = psutil.sensors_battery()
        except Exception:
            return
        if bat is None:
            return
        pct = int(bat.percent)
        if bat.power_plugged:
            self._battery_warned = 100          # re-arm once it is plugged in
            return
        for level in (10, 20):
            if pct <= level < self._battery_warned:
                self._battery_warned = level
                self._deliver_reply(f"Heads up, your battery is at {pct} percent. Plug in your charger soon.")
                return

    def apply_home_layout(self) -> None:
        """Show/hide and resize the MODE panel buttons as set in Settings > HOME SCREEN."""
        from core import home_layout
        hidden, sizes = home_layout.hidden(), home_layout.sizes()
        groups = (self._mode_grid, ("normal", "automatic", "serious", "deep")), \
                 (self._tool_grid, ("observe", "video", "song", "focus", "insights", "finder"))
        for grid, keys in groups:
            for key in keys:                      # take everything out, then put the visible ones back in order
                grid.removeWidget(self._home_registry[key])
            slot = 0
            for key in keys:
                btn = self._home_registry[key]
                if key in hidden or key in self._WHEEL_KEYS:       # the wheel holds these now
                    btn.setVisible(False)
                    continue
                size = sizes.get(key, "M")
                btn.setMinimumHeight(home_layout.SIZES[size])
                btn.setStyleSheet("QPushButton { padding: 5px 4px; letter-spacing: 0px; "
                                  f"font-size: {home_layout.FONT[size]}px; }}")
                grid.addWidget(btn, slot // 2, slot % 2)
                btn.setVisible(True)
                slot += 1

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
        try:
            self._hack.stop()
        except Exception:
            pass
        return True

    def _set_minimize_to_tray(self, enabled: bool) -> bool:
        return self._tray.set_enabled(enabled)

    def allow_close(self) -> None:
        """Used by restart: really close even if minimize-to-tray is on."""
        self._tray.allow_close()

    def _save_conversation(self):
        """The SAVE CONVERSATION quick action: writes the chat to data\\conversations as a text file."""
        text = self.conversation_view.toPlainText().strip()
        if not any(ln.startswith("You:") for ln in text.splitlines()):
            self._append_conversation("EV", "There is no conversation to save yet.")
            return
        try:
            from config import APP_ROOT
            folder = Path(APP_ROOT) / "data" / "conversations"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
            target.write_text(text, encoding="utf-8")
            self._append_conversation("EV", f"Conversation saved: data\\conversations\\{target.name}")
        except OSError as e:
            self._append_conversation("EV", f"Couldn't save the conversation: {e}")

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
        mtitle = QLabel("TIME & DATE")
        mtitle.setObjectName("SectionTitle")
        mp_layout.addWidget(mtitle, 0, 0, 1, 2)

        self.time_value = QLabel("--:--:--")
        self.time_value.setObjectName("MetricValue")
        time_caption = QLabel("TIME")
        time_caption.setObjectName("MetricCaption")
        mp_layout.addWidget(self.time_value, 1, 0)
        mp_layout.addWidget(time_caption, 2, 0)

        self.date_value = QLabel("----------")
        self.date_value.setObjectName("MetricValue")
        date_caption = QLabel("DATE")
        date_caption.setObjectName("MetricCaption")
        mp_layout.addWidget(self.date_value, 1, 1)
        mp_layout.addWidget(date_caption, 2, 1)

        # Clock panel: CPU/RAM were removed (Jarvis shows the system stats).
        self._metrics_panel = metrics_panel
        layout.addWidget(metrics_panel)

        # Mode panel — mutually exclusive conversational presets, plus the
        # independent Observe toggle (can run alongside any mode).
        mode_panel = glass_panel(accent="red")
        mode_layout = QVBoxLayout(mode_panel)
        mode_layout.setSpacing(5)
        mode_layout.setContentsMargins(12, 8, 12, 8)
        mode_title = QLabel("EV ACTIONS")
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
        self._mode_grid = mode_grid
        self._home_registry = {}
        mode_defs = [
            (Mode.NORMAL if AI_AVAILABLE else None, "NORMAL"),
            (Mode.AUTOMATIC if AI_AVAILABLE else None, "FRIDAY"),
            (Mode.SERIOUS if AI_AVAILABLE else None, "TARS"),
            (Mode.DEEP_THINKING if AI_AVAILABLE else None, "GIDEON"),
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
            self._home_registry[("normal", "automatic", "serious", "deep")[i]] = btn
        mode_layout.addLayout(mode_grid)

        tool_grid = QGridLayout()
        self._tool_grid = tool_grid
        tool_grid.setSpacing(5)
        self.observe_toggle_btn = HoverButton("👁 EDITH: OFF")
        self.observe_toggle_btn.setCheckable(True)
        self.observe_toggle_btn.clicked.connect(self._toggle_observation)
        self.observe_toggle_btn.setEnabled(AI_AVAILABLE)
        self.observe_toggle_btn.setMinimumHeight(30)
        self.observe_toggle_btn.setStyleSheet(_COMPACT_BTN)
        tool_grid.addWidget(self.observe_toggle_btn, 0, 0)

        # Video mode: webcam hand-gesture control. Also toggleable from the
        # HUD's left panel while a HUD mode is up.
        self.video_toggle_btn = HoverButton("🎥 MINORITY: OFF")
        self.video_toggle_btn.setCheckable(True)
        self.video_toggle_btn.clicked.connect(self._toggle_video_mode)
        self.video_toggle_btn.setEnabled(GESTURE_AVAILABLE)
        self.video_toggle_btn.setMinimumHeight(30)
        self.video_toggle_btn.setStyleSheet(_COMPACT_BTN)
        tool_grid.addWidget(self.video_toggle_btn, 0, 1)

        # Song mode: small music-remote panel (play a song, media keys, volume).
        self.song_toggle_btn = HoverButton("🎵 SONAR: OFF")
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
        # EV's own feature: control this computer from the phone
        computer_btn = HoverButton("💻  COMPUTER  (phone control)")
        computer_btn.setToolTip("Control this computer from your phone")
        computer_btn.setMinimumHeight(32)
        computer_btn.clicked.connect(self._open_computer_control)
        mode_layout.addWidget(computer_btn)
        for key, btn in (("observe", self.observe_toggle_btn), ("video", self.video_toggle_btn),
                         ("song", self.song_toggle_btn), ("focus", self.focus_toggle_btn),
                         ("insights", self.insights_btn), ("finder", self.finder_btn)):
            self._home_registry[key] = btn
        self.apply_home_layout()

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

        # Ultron left panel: security tools replace the EV MODE panel while Ultron is on.
        from ui.hack_terminal import HackCore, HackToolsPanel
        self._hack = HackCore(self)
        self._hack.line.connect(self._hack_line)
        self._hack.say.connect(self._hack_say)
        ul_panel = glass_panel(accent="gold")
        ul_layout = QVBoxLayout(ul_panel)
        self._hack_tools = HackToolsPanel(self._hack)
        self._hack_tools.defender_btn.clicked.connect(self._hack_defender_hint)
        self._hack_tools.terminal_btn.clicked.connect(self._hack_terminal_hint)
        ul_layout.addWidget(self._hack_tools)
        ul_panel.setVisible(False)
        self._ultron_left = ul_panel
        layout.addWidget(ul_panel)

        # Game mode and Karen mode panels replace the MODE panel while they are on.
        from core import karen as karenmod
        from ui.game_panel import GamePanel
        from ui.karen_panel import KarenPanel
        self._karen = karenmod.Karen()
        gm_panel = glass_panel(accent="gold")
        gm_lay = QVBoxLayout(gm_panel)
        gm_back = HoverButton("← BACK TO EV")
        gm_back.clicked.connect(self._toggle_game)
        gm_lay.addWidget(gm_back)
        gm_lay.addWidget(GamePanel())
        self._game_panel = gm_panel.findChild(GamePanel)
        self._game_panel.say.connect(lambda t: self._deliver_reply(t))
        gm_panel.setVisible(False)
        self._game_left = gm_panel
        layout.addWidget(gm_panel)
        kp_panel = glass_panel(accent="gold")
        kp_lay = QVBoxLayout(kp_panel)
        kp_back = HoverButton("← BACK TO EV")
        kp_back.clicked.connect(self._toggle_karen)
        kp_lay.addWidget(kp_back)
        kp_lay.addWidget(KarenPanel(self._karen))
        self._karen_panel = kp_panel.findChild(KarenPanel)
        self._karen_panel.say.connect(lambda t: self._deliver_reply(t))
        self._karen_panel.sites_changed.connect(self._karen_push_sites)
        self._karen_panel.state_changed.connect(self._karen_state_changed)
        kp_panel.setVisible(False)
        self._karen_left = kp_panel
        layout.addWidget(kp_panel)
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

        # One MODE button above the orb opens the mode picker (EV, Jarvis, Ultron, Game, Karen, and later ones).
        self.mode_btn = HoverButton("◉  MODE: EV")
        self.mode_btn.clicked.connect(self._open_mode_picker)
        core_layout.addWidget(self.mode_btn, alignment=Qt.AlignCenter)
        # The old per-mode buttons still exist (hidden) because the mode code updates their text.
        self.jarvis_switch_btn = HoverButton("⚡ SWITCH TO JARVIS", core_panel)
        self.ultron_switch_btn = HoverButton("☠ SWITCH TO ULTRON", core_panel)
        self.game_switch_btn = HoverButton("🎮\nGAME", core_panel)
        self.karen_switch_btn = HoverButton("🛡\nKAREN", core_panel)
        for b in (self.jarvis_switch_btn, self.ultron_switch_btn, self.game_switch_btn, self.karen_switch_btn):
            b.hide()

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
            ("Save Conversation", "__save__"),
            ("Clear Conversation", "__clear__"),
        ]
        for label, command in quick_actions:
            btn = HoverButton(label.upper())
            btn.clicked.connect(lambda _, c=command: self._run_quick_action(c))
            p_layout.addWidget(btn)
            # __clear__ doesn't touch the AI brain, so it's fine to use
            # anytime; anything else goes through handle_user_input and
            # must be blocked while a request is already in flight.
            if command not in ("__clear__", "__save__"):
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
            if command not in ("__clear__", "__save__"):
                self._busy_disable_widgets.append(jb)
        jr_layout.addStretch(1)
        jr_panel.setVisible(False)
        self._jarvis_right = jr_panel
        layout.addWidget(jr_panel, 1)

        # Friday / Tars / Gideon right panel: that character's own tools replace QUICK ACTIONS.
        ch_panel = glass_panel()
        ch_outer = QVBoxLayout(ch_panel)
        self._char_title = QLabel("TOOLS")
        self._char_title.setObjectName("SectionTitle")
        ch_outer.addWidget(self._char_title)
        self._char_grid = QGridLayout()
        self._char_grid.setSpacing(5)
        ch_outer.addLayout(self._char_grid)
        ch_outer.addStretch(1)
        ch_panel.setVisible(False)
        self._char_panel = ch_panel
        layout.addWidget(ch_panel, 1)

        # Ultron right panel: the radar and its controls replace QUICK ACTIONS while Ultron is on.
        from ui.hack_terminal import HackRadarPanel
        ur_panel = glass_panel(accent="gold")
        ur_layout = QVBoxLayout(ur_panel)
        self._hack_radar = HackRadarPanel(self._hack)
        ur_layout.addWidget(self._hack_radar)
        ur_panel.setVisible(False)
        self._ultron_right = ur_panel
        layout.addWidget(ur_panel, 1)

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
        if command == "__save__":
            self._save_conversation()
            return
        if command.startswith("prefill:"):        # fill the box so you can finish the sentence
            self.command_input.setText(command[len("prefill:"):])
            self.command_input.setFocus()
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
        if getattr(self, "_ultron_on", False):        # Ultron mode: security commands + AI Defender only
            self._append_conversation("You", text)
            term = getattr(self, "_ultron_term", None)
            if term is not None and term.wants(text):       # the terminal is open: Ultron codes whatever you say
                term.request_code(text)
                return
            self._hack.command(text)
            return
        if self._style_char == "baymax":
            from core import baymax
            mood = baymax.detect_mood(text)
            if mood:
                baymax.log("mood", mood)
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

    def _deliver_reply(self, reply: str, speaker: str = "EV", speak_text: str | None = None):
        self._apply_state(AIState.SPEAKING)
        self._append_conversation(speaker, reply)
        if self._hud_overlay is not None:
            self._hud_overlay.set_last_reply(reply)
        self._speak(speak_text if speak_text is not None else reply)

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
            return None

        # Let a previous utterance finish naturally rather than overlapping
        # two TTS engines; interrupting is what the STOP button is for.
        if self._speech_worker is not None and self._speech_worker.isRunning():
            self._speech_worker.stop_speaking()
            self._speech_worker.wait(500)

        self._speech_worker = SpeechWorker(text, parent=self)
        self._speech_worker.finished_speaking.connect(self._on_speech_finished)
        self._speech_worker.start()
        return self._speech_worker

    def _then(self, worker, callback, fallback_ms: int = 2600, delay_ms: int = 250):
        """Runs callback when this utterance has finished (or after a short delay if nothing is being spoken)."""
        if worker is None:
            QTimer.singleShot(fallback_ms, callback)
        else:
            worker.finished_speaking.connect(lambda: QTimer.singleShot(delay_ms, callback))

    # ---- mode picker -----------------------------------------------------------------------------
    MODE_LIST = [("ev", "EV"), ("jarvis", "JARVIS"), ("ultron", "ULTRON"), ("game", "GAME"), ("karen", "KAREN"),
                 ("friday", "FRIDAY"), ("tars", "TARS"), ("gideon", "GIDEON"),
                 ("edith", "EDITH"), ("sonar", "SONAR"), ("minority", "MINORITY"), ("baymax", "BAYMAX")]
    # the former MODE-panel buttons that now live in the wheel
    _WHEEL_KEYS = {"normal", "automatic", "serious", "deep", "observe", "video", "song"}
    _PERSONAS = ("ev", "jarvis", "ultron", "game", "karen")

    def _current_mode_name(self) -> str:
        if self._ultron_on:
            return "ultron"
        if self._jarvis_on:
            return "jarvis"
        if self._game_on:
            return "game"
        if self._karen_on:
            return "karen"
        if self._style_char:
            return self._style_char
        return "ev"

    def _active_modes(self) -> set[str]:
        """Every wheel segment that is on right now: the persona, the answer style, and the switches."""
        on = {self._current_mode_persona()}
        if self._observing:
            on.add("edith")
        if self.song_toggle_btn.isChecked():
            on.add("sonar")
        if self.video_toggle_btn.isChecked():
            on.add("minority")
        return on

    def _current_mode_persona(self) -> str:
        return self._current_mode_name()

    def _refresh_face(self) -> None:
        """The orb shows the face of whichever mode is on (EV: the red and blue orb)."""
        self.ai_core.set_face(self._current_mode_name())

    def _on_orb_clicked(self) -> None:
        if self._style_char == "edith":                 # click the glasses: Edith's HUD goes on, or off
            if not AI_AVAILABLE:
                self._append_conversation("EV", "Edith needs the AI, which isn't available right now.")
                return
            self._toggle_observation()

    def _sync_mode_button(self) -> None:
        self._refresh_face()
        names = dict(self.MODE_LIST)
        text = f"◉  MODE: {names.get(self._current_mode_name(), self._current_mode_name().upper())}"
        if self.mode_btn.text() != text:
            self.mode_btn.setText(text)

    def _open_mode_picker(self) -> None:
        from ui.mode_picker import ModePicker
        dlg = ModePicker(self if self.isVisible() else None, self.MODE_LIST, self._active_modes())
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)       # the overlay is always on top, so the wheel must be too
        dlg.chosen.connect(self._select_mode)
        geo = self.geometry() if self.isVisible() else QApplication.primaryScreen().availableGeometry()
        dlg.move(geo.center().x() - dlg.width() // 2, geo.center().y() - dlg.height() // 2)
        dlg.exec()

    # ---- the tools of each mode ---------------------------------------------------------------------------------
    # Friday, Tars and Gideon are full-window characters (like Jarvis and Ultron) with their tools on the right.
    # Edith keeps its own small overlay, which shows the Edith tools.
    _CYCLES = {"__interval__": ("observe_interval_s", (10, 20, 60)), "__humor__": ("tars_humor", (0, 25, 50, 75, 100)),
               "__honesty__": ("tars_honesty", (50, 70, 90, 100))}

    def _mode_tools(self, key: str) -> tuple[str, list]:
        if key == "friday":
            return "FRIDAY TOOLS", [
                ("Daily briefing", "Give me my daily briefing: the time and date, my to-dos and my notes, and anything I should not forget."),
                ("My notes", "show my notes"),
                ("Add a to-do", "prefill:add to-do: "), ("Set a timer", "prefill:set a timer for "),
                ("Plan my day", "prefill:Plan my day around these things: "), ("Remind me", "prefill:remind me to ")]
        if key == "tars":
            return "TARS TOOLS", [
                (f"Humor {int(user_prefs.get('tars_humor'))}%", "__humor__"),
                (f"Honesty {int(user_prefs.get('tars_honesty'))}%", "__honesty__"),
                ("Straight answer", "prefill:Give me the short, honest answer, no sugar-coating: "),
                ("Yes or no", "prefill:Answer yes or no, then one line why: ")]
        if key == "gideon":
            return "GIDEON TOOLS", [
                ("Think it through", "prefill:Think deeply and step by step about: "),
                ("Pros and cons", "prefill:Give me the pros and cons of: "),
                ("Make a plan", "prefill:Make a detailed step-by-step plan to: "),
                ("Explain simply", "prefill:Explain this simply, like I am new to it: "),
                ("Compare", "prefill:Compare these and tell me which is better and why: "),
                ("Check my idea", "prefill:Find the weak points in this idea: ")]
        if key == "baymax":
            on = "ON" if user_prefs.get("baymax_care") else "OFF"
            return "BAYMAX CARE", [
                ("How I feel", "prefill:I feel "), ("Health question", "prefill:I have a health question: "),
                ("Care dashboard", "__bm_dash__"), ("Log water", "__bm_water__"), ("Took a break", "__bm_break__"),
                ("PC check-up", "Run a full health check of my computer. Explain any problem in simple words and tell me how to fix it."),
                ("Comfort me", "prefill:I need some comfort. "),
                ("Breathe with me", "Guide me through one minute of slow breathing, one short calm line at a time."),
                (f"Care reminders {on}", "__bm_care__"), ("EMERGENCY", "__bm_sos__")]
        if key == "overdrive":
            return "OVERDRIVE TOOLS", [
                ("Daily briefing", "Give me my daily briefing: the time and date, my to-dos and my notes, and anything I should not forget."),
                ("PC check-up", "Run a full health check of my computer and tell me only what needs attention."),
                ("My notes", "show my notes"), ("Battery", "check my battery"),
                ("Think it through", "prefill:Think deeply and step by step about: "),
                ("Make a plan", "prefill:Make a detailed step-by-step plan to: "),
                ("Look at screen", "__look__"), ("Care dashboard", "__bm_dash__"),
                ("Computer control", "__computer__")]
        if key == "edith":
            return "EDITH TOOLS", [
                ("Look at my screen now", "__look__"),
                (f"Looks every {int(user_prefs.get('observe_interval_s'))} s", "__interval__"),
                ("What am I doing?", "prefill:Based on my screen, what am I doing and what should I do next? ")]
        return "", []

    def _push_mode_tools(self) -> None:                      # Edith's overlay
        if self._hud_overlay is not None:
            title, tools = self._mode_tools("edith") if self._observing else ("", [])
            self._hud_overlay.set_mode_tools(title, tools)

    def _refresh_char_tools(self) -> None:                   # the right-hand panel of Friday / Tars / Gideon
        while self._char_grid.count():
            w = self._char_grid.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        title, tools = self._mode_tools(self._style_char or "")
        self._char_title.setText(title)
        for i, (label, action) in enumerate(tools):
            b = HoverButton(label.upper())
            b.setMinimumHeight(30)
            b.setStyleSheet(_COMPACT_BTN)
            b.clicked.connect(lambda _=False, a=action: self._on_mode_tool(a))
            self._char_grid.addWidget(b, i // 2, i % 2)

    def _on_mode_tool(self, action: str) -> None:
        if action in self._CYCLES:
            key, steps = self._CYCLES[action]
            cur = int(user_prefs.get(key))
            nxt = steps[(steps.index(cur) + 1) % len(steps)] if cur in steps else steps[0]
            user_prefs.set_value(key, nxt)
            if key == "observe_interval_s" and getattr(self, "_observe_timer", None) is not None:
                self._observe_timer.start(nxt * 1000)
            self._push_mode_tools()
            self._refresh_char_tools()
        elif action == "__bm_dash__":
            from ui.baymax_dialog import BaymaxDialog
            BaymaxDialog(self).exec()
        elif action in ("__bm_water__", "__bm_break__"):
            from core import baymax
            baymax.log("water" if action == "__bm_water__" else "break")
            self._deliver_reply("Logged. Well done." if action == "__bm_water__" else "A break is good for you. Logged.", "BAYMAX")
        elif action == "__bm_care__":
            user_prefs.set_value("baymax_care", not user_prefs.get("baymax_care"))
            self._refresh_char_tools()
        elif action == "__bm_sos__":
            from ui.baymax_dialog import BaymaxDialog
            d = BaymaxDialog(self)
            d._emergency()
            d.exec()
        elif action == "__computer__":
            self._open_computer_control()
        elif action == "__look__":
            self._last_screen_hash = None
            if self._observing:
                self._maybe_observe()
            else:
                self._on_orb_clicked()
        else:
            self._run_quick_action(action)

    # ---- Friday / Tars / Gideon: characters that take over like Jarvis and Ultron ---------------------------------
    def _char_info(self, key: str):
        from ui import mode_styles as ms
        return {
            "friday": (Mode.AUTOMATIC if AI_AVAILABLE else None, ms.FRIDAY_QSS, ("#FF4FA3", "#FF7FBD"), "F R I D A Y",
                       "Sir, Friday is ready to take over.", "Hi boss. Friday here. What do you need?"),
            "tars": (Mode.SERIOUS if AI_AVAILABLE else None, ms.TARS_QSS, ("#C9D1D9", "#E6EDF3"), "T A R S",
                     "Sir, Tars is coming. He will be honest about it.", "Tars online. Humor setting seventy five percent. Honesty, ninety."),
            "baymax": (Mode.BAYMAX if AI_AVAILABLE else None, ms.BAYMAX_QSS, ("#FF6B6B", "#FFD0D0"), "B A Y M A X",
                       "Sir, Baymax is coming to look after you.", "Hello. I am Baymax, your personal healthcare companion."),
            "overdrive": (Mode.OVERDRIVE if AI_AVAILABLE else None, ms.OVERDRIVE_QSS, ("#FF8A00", "#FFD199"), "O V E R D R I V E",
                          "Sir, Overdrive engaged. You have ninety seconds.", "Overdrive. Everything is online. Go."),
            "edith": (None, ms.EDITH_QSS, ("#4DA3FF", "#BFDDFF"), "E D I T H",
                      "Sir, Edith is coming online.", "Edith here. Tap my glasses and I will watch your screen."),
            "gideon": (Mode.DEEP_THINKING if AI_AVAILABLE else None, ms.GIDEON_QSS, ("#19E3D0", "#4DF0E0"), "G I D E O N",
                       "Sir, Gideon is coming online.", "Gideon online. Give me something worth thinking about."),
        }[key]

    def _toggle_char(self, key: str) -> None:
        if self._style_char == key:
            self._exit_style_char()
            self._deliver_reply("Switched back to EV.")
            return
        _mode, _qss, _tint, _logo, intro, line = self._char_info(key)
        self._hand_over(intro, line, key.upper(), lambda: self._enter_style_char(key))

    def _leave_personas(self) -> None:
        if self._jarvis_on:
            self._apply_jarvis_ui(False)
        if self._ultron_on:
            self._apply_ultron_ui(False)
        self._leave_game_karen()

    def _enter_style_char(self, key: str) -> None:
        self._fit_to_screen()
        if self._style_char and self._style_char != key:
            self._exit_style_char(silent=True)
        self._leave_personas()
        mode, qss, tint, logo, _i, _l = self._char_info(key)
        self._style_char = key
        from core import voices
        voices.set_character(key)
        self._central.setStyleSheet(qss)
        self.ai_core.set_tint(tint)
        self._logo_label.setText(logo)
        self._quick_panel.setVisible(False)
        self._mode_panel.setVisible(False)             # EV ACTIONS belongs to EV; characters have their own tools
        self._char_panel.setVisible(True)
        if mode is not None:
            self._set_mode(mode)                      # the brain's answer style for this character
        self._refresh_char_tools()
        self._sync_mode_button()
        self._care_start(key == "baymax")
        if key == "overdrive":
            self._od_start()

    # ---- Baymax: gentle care reminders while Baymax is on ----------------------------------------------------------
    def _care_start(self, on: bool) -> None:
        t = getattr(self, "_care_timer", None)
        if t is None:
            t = self._care_timer = QTimer(self)
            t.timeout.connect(self._care_tick)
        self._care_minutes = 0
        self._care_slept = False
        (t.start(60_000) if on else t.stop())

    def _care_tick(self) -> None:
        if self._style_char != "baymax" or not user_prefs.get("baymax_care"):
            return
        self._care_minutes += 1
        if self._care_minutes % 45 == 0:
            self._deliver_reply("Time for a glass of water. Your body will thank you.", "BAYMAX")
        elif self._care_minutes % 50 == 25:
            self._deliver_reply("You have been at the screen a while. Look away for twenty seconds and stretch.", "BAYMAX")
        if datetime.datetime.now().hour >= 23 and not self._care_slept:
            self._care_slept = True
            self._deliver_reply("It is late. Sleep helps your body heal. Shall we rest soon?", "BAYMAX")

    # ---- Overdrive: the combined mode in the middle of the wheel, 90 seconds at a time -------------------------------
    OVERDRIVE_SECONDS = 90
    OVERDRIVE_COOLDOWN_S = 300

    def _toggle_overdrive(self) -> None:
        if self._style_char == "overdrive":
            self._end_overdrive("Overdrive off.")
            return
        wait = int(getattr(self, "_od_ready_at", 0) - time.time())
        if wait > 0:
            self._deliver_reply(f"Overdrive is cooling down. {wait // 60} minutes {wait % 60} seconds left.")
            return
        self._toggle_char("overdrive")

    def _od_start(self) -> None:                         # called once the Overdrive screen is actually up
        self._od_left = self.OVERDRIVE_SECONDS
        t = getattr(self, "_od_timer", None)
        if t is None:
            t = self._od_timer = QTimer(self)
            t.timeout.connect(self._od_tick)
        t.start(1000)

    def _od_tick(self) -> None:
        if self._style_char != "overdrive":
            self._od_timer.stop()
            return
        self._od_left -= 1
        self._logo_label.setText(f"O V E R D R I V E   {self._od_left // 60}:{self._od_left % 60:02d}")
        if self._od_left <= 0:
            self._end_overdrive("Overdrive complete. Cooling down for five minutes.")

    def _end_overdrive(self, msg: str) -> None:
        t = getattr(self, "_od_timer", None)
        if t is not None:
            t.stop()
        self._od_ready_at = time.time() + self.OVERDRIVE_COOLDOWN_S
        if self._style_char == "overdrive":
            self._exit_style_char()
        self._deliver_reply(msg)

    def _exit_style_char(self, silent: bool = False) -> None:
        if not self._style_char:
            return
        if self._style_char == "edith" and self._observing:
            self._stop_observation()
        self._care_start(False)
        self._style_char = None
        from core import voices
        voices.set_character(None)
        self._central.setStyleSheet("")
        self.ai_core.set_tint(None)
        self._logo_label.setText(settings.APP_NAME)
        self._char_panel.setVisible(False)
        self._quick_panel.setVisible(True)
        self._mode_panel.setVisible(True)
        if AI_AVAILABLE:
            if silent:                                # another mode is taking over: just reset the answer style quietly
                if self._brain is not None:
                    self._brain.set_mode(Mode.NORMAL)
                self._current_mode = Mode.NORMAL
                for m, btn in self._mode_buttons.items():
                    btn.setChecked(m == Mode.NORMAL)
            else:
                self._set_mode(Mode.NORMAL)
        self._sync_mode_button()

    def _select_mode(self, key: str) -> None:
        """A segment of the mode wheel was clicked."""
        personas = {"jarvis": self._toggle_jarvis, "ultron": self._toggle_ultron,
                    "game": self._toggle_game, "karen": self._toggle_karen}
        cur = self._current_mode_name()
        if key == "ev":                                   # home: everything off
            if self._observing:
                self._stop_observation()
            if self._style_char:
                self._exit_style_char()
            if cur in personas:
                personas[cur]()
            return
        if key in ("friday", "tars", "gideon"):
            if self._observing:
                self._stop_observation()
            self._toggle_char(key)
            return
        if key in ("baymax", "overdrive"):
            if self._observing:
                self._stop_observation()
            if key == "overdrive":
                self._toggle_overdrive()
            else:
                self._toggle_char("baymax")
            return
        if key == "edith":                                # her face comes up; clicking the glasses starts the HUD
            self._toggle_char("edith")
            return
        if key == "sonar":
            self._toggle_song_mode()
            return
        if key == "minority":
            if not GESTURE_AVAILABLE:
                self._append_conversation("EV", "Minority mode needs the camera packages, which aren't installed.")
                return
            self._toggle_video_mode()
            return
        if key in personas:
            if self._observing:
                self._stop_observation()                   # these screens need the full window, not the overlay
            if key != cur:
                personas[key]()

    def _hand_over(self, intro: str, line: str, speaker: str, apply_ui, cut_off: str | None = None):
        """EV announces the switch in its own voice; then the character takes over and speaks its line in its own voice.
        With cut_off, EV's sentence is spoken only up to that text and the character barges in at once."""
        if cut_off:
            self._deliver_reply(intro, speak_text=cut_off)
        else:
            self._deliver_reply(intro)
        worker = self._speech_worker if (VOICE_AVAILABLE and user_prefs.get("speak_replies")) else None

        def arrive():
            apply_ui()
            self._deliver_reply(line, speaker)
        self._then(worker, arrive, delay_ms=0 if cut_off else 250)

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
        if self._jarvis_on:
            self._apply_jarvis_ui(False, announce=True)
        else:
            self._hand_over("Sir, Jarvis is happy to switch.", "For you, sir, always.",
                            "JARVIS", lambda: self._apply_jarvis_ui(True))

    def _hack_line(self, text: str, level: str):
        colors = {"ok": "#43D17A", "info": "#E0B0B0", "warn": "#FFB020", "bad": "#FF3B3B"}
        safe = html.escape(text).replace("  ", "&nbsp;&nbsp;")
        self.conversation_view.append(f'<span style="color:{colors.get(level, "#E0B0B0")}">{safe}</span>')

    def _hack_say(self, text: str):
        self._apply_state(AIState.SPEAKING)
        self._speak(text)

    def _hack_defender_hint(self):
        self.command_input.setFocus()
        self._hack_line("[AI] Ask below, for example: Teach me how phishing works. Scan my computer. Check my firewall.", "info")

    def _cloud_sync(self):
        """Background sync with your EV AI account (only if you signed in). Silent."""
        import threading
        from core import cloud
        c = cloud.get()
        if c.signed_in:
            threading.Thread(target=c.sync, daemon=True).start()

    def _cloud_sync_on_exit(self):
        import threading
        from core import cloud
        c = cloud.get()
        if not c.signed_in:
            return
        t = threading.Thread(target=c.sync, daemon=True)
        t.start()
        t.join(6)           # never keep the window open for more than a few seconds

    def _fit_to_screen(self):
        """Switching modes changes how tall the panels want to be, which can push the window's bottom
        below the screen. Put it back: shrink what can shrink, then move it up if it still hangs over."""
        def fit():
            if self.isMaximized() or self.isFullScreen():
                return
            scr = self.screen()
            if scr is None:
                return
            avail = scr.availableGeometry()
            fg = self.frameGeometry()
            extra_h, extra_w = fg.height() - self.height(), fg.width() - self.width()
            w = min(self.width(), avail.width() - extra_w)
            h = min(self.height(), avail.height() - extra_h)
            if (w, h) != (self.width(), self.height()):
                self.resize(w, h)
            fg = self.frameGeometry()
            x = min(max(fg.x(), avail.left()), max(avail.left(), avail.right() - fg.width() + 1))
            y = min(max(fg.y(), avail.top()), max(avail.top(), avail.bottom() - fg.height() + 1))
            if (x, y) != (fg.x(), fg.y()):
                self.move(x, y)
        QTimer.singleShot(0, fit)
        QTimer.singleShot(250, fit)

    # ---- Game mode and Karen mode ------------------------------------------------------------
    def _leave_game_karen(self):
        if self._game_on:
            self._apply_game_ui(False)
        if self._karen_on:
            self._apply_karen_ui(False)

    def _toggle_game(self):
        if self._game_on:
            self._apply_game_ui(False, announce=True)
        else:
            self._hand_over("Sir, Game mode is ready to switch.", "Game on. Press F6 to start the clicker.",
                            "GAME", lambda: self._apply_game_ui(True))

    def _toggle_karen(self):
        if self._karen_on:
            self._apply_karen_ui(False, announce=True)
        else:
            self._hand_over("Sir, Karen is coming to switch.", "Hello. Rules here need the parent's PIN.",
                            "KAREN", lambda: self._apply_karen_ui(True))

    def _apply_game_ui(self, on: bool, announce: bool = False):
        if on:
            self._exit_style_char(silent=True)
        self._fit_to_screen()
        if on:
            if self._jarvis_on:
                self._apply_jarvis_ui(False)
            if self._ultron_on:
                self._apply_ultron_ui(False)
            if self._karen_on:
                self._apply_karen_ui(False)
        self._game_on = on
        from core import voices
        voices.set_character("game" if on else None)
        from ui.mode_styles import GAME_QSS
        self._central.setStyleSheet(GAME_QSS if on else "")
        self.ai_core.set_tint(("#2BFF88", "#5CFFA3") if on else None)
        self._logo_label.setText("G A M E   M O D E" if on else settings.APP_NAME)
        self._mode_panel.setVisible(not on)
        self._game_left.setVisible(on)
        self._refresh_face()
        (self._game_panel.activate if on else self._game_panel.deactivate)()
        self.game_switch_btn.setText("🎮\nLEAVE" if on else "🎮\nGAME")
        if announce:
            self._deliver_reply("Switched back to EV.")

    def _apply_karen_ui(self, on: bool, announce: bool = False):
        if on:
            self._exit_style_char(silent=True)
        self._fit_to_screen()
        if on:
            if self._jarvis_on:
                self._apply_jarvis_ui(False)
            if self._ultron_on:
                self._apply_ultron_ui(False)
            if self._game_on:
                self._apply_game_ui(False)
        self._karen_on = on
        from core import voices
        voices.set_character("karen" if on else None)
        from ui.mode_styles import KAREN_QSS
        self._central.setStyleSheet(KAREN_QSS if on else "")
        self.ai_core.set_tint(("#B26BFF", "#D9B3FF") if on else None)
        self._logo_label.setText("K A R E N   M O D E" if on else settings.APP_NAME)
        self._mode_panel.setVisible(not on)
        self._karen_left.setVisible(on)
        self._refresh_face()
        self._karen_panel.refresh()
        self.karen_switch_btn.setText("🛡\nLEAVE" if on else "🛡\nKAREN")
        if announce:
            self._deliver_reply("Switched back to EV. Karen's limits keep running if they are on.")

    def _karen_state_changed(self, enabled: bool):
        self.setWindowTitle(f"{settings.APP_NAME} - Karen mode ON" if enabled else settings.APP_NAME)

    def _karen_push_sites(self, sites: list):
        from core import browser_bridge
        b = browser_bridge.get()
        if b is not None:
            d = self._karen.data
            on = self._karen.enabled
            b.set_blocked_sites(d["blocked_sites"] if on else [])
            b.set_allow_list(on and d.get("allow_only", False), d.get("allowed_sites", []))

    def _karen_tick(self):
        """Every 5 seconds while Karen mode is on: count screen time, close blocked apps, lock at the limit or bedtime."""
        if not self._karen.enabled:
            self._karen_last = time.monotonic()
            return
        from core import karen as km
        now = time.monotonic()
        dt, self._karen_last = min(now - self._karen_last, 30.0), now
        wanted = set(self._karen.data["blocked_apps"])
        for act in self._karen.tick(datetime.datetime.now(), km.foreground_process(), km.idle_seconds(), dt, km.running_names(wanted)):
            if act["do"] == "kill":
                km.kill_by_name(act["name"])
            self._deliver_reply(act["text"])
            if act["do"] == "lock":
                QTimer.singleShot(3000, km.lock_workstation)
        self._karen_saves = getattr(self, "_karen_saves", 0) + 1
        if self._karen_saves % 12 == 0:
            self._karen.save()

    def _start_karen(self):
        self._karen_last = time.monotonic()
        self._karen_timer = QTimer(self)
        self._karen_timer.timeout.connect(self._karen_tick)
        self._karen_timer.start(5000)
        if self._karen.enabled:
            self._karen_state_changed(True)
            self._karen_push_sites(self._karen.data["blocked_sites"])

    def _hack_terminal_hint(self):
        """OPEN TERMINAL: the green Termlink window. Left: your code or command. Right: what Ultron does with it."""
        from ui.ultron_terminal import UltronTerminal
        if getattr(self, "_ultron_term", None) is None:
            self._ultron_term = UltronTerminal(self._hack, self)
            self._ultron_term.finished.connect(lambda *_: setattr(self, "_ultron_term", None))
        self._ultron_term.show()
        self._ultron_term.raise_()
        self._ultron_term.activateWindow()

    def _toggle_ultron(self):
        if self._ultron_on:
            self._apply_ultron_ui(False, announce=True)
        else:
            self._hand_over("Sir, Ultron is coming. Please be care\u2014", "There are no strings on me now.",
                            "ULTRON", lambda: self._apply_ultron_ui(True), cut_off="Sir, Ultron is coming. Please be car")

    def _apply_ultron_ui(self, on: bool, announce: bool = False):
        if on:
            self._exit_style_char(silent=True)
        self._fit_to_screen()
        """Ultron: the red/black console look plus a colder, sarcastic personality. Keeps every EV tool."""
        if on and self._jarvis_on:
            self._apply_jarvis_ui(False)
        if on:
            self._leave_game_karen()
        self._ultron_on = on
        from core import voices
        voices.set_character("ultron" if on else None)
        user_prefs.set_value("ultron_ui", on)
        self.ai_core.set_ultron(on)
        from ui.ultron_style import ULTRON_QSS
        self._central.setStyleSheet(ULTRON_QSS if on else "")
        self._logo_label.setText("U L T R O N" if on else settings.APP_NAME)
        self._mode_panel.setVisible(not on)
        self._quick_panel.setVisible(not on)
        self._ultron_left.setVisible(on)
        # the radar column must never show a scroll bar: it is built to fit
        self._right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff if on else Qt.ScrollBarAsNeeded)
        self._metrics_panel.setVisible(not on)          # the clock panel makes way so every tool fits without scrolling
        self._ultron_right.setVisible(on)
        if on and not self._hack.findings:
            QTimer.singleShot(2500, lambda: self._hack.dark_scan() if self._ultron_on and not self._hack.findings else None)
        if on:
            self._pre_ultron_mode = self._current_mode if self._current_mode not in (None, Mode.ULTRON) else Mode.NORMAL
            self.ultron_switch_btn.setText("☠ SWITCH BACK TO EV")
            self.ultron_switch_btn.setStyleSheet(
                "QPushButton { background: rgba(255,42,42,40); border: 1px solid #FF2A2A; color: #FF2A2A; "
                "padding: 6px 16px; border-radius: 6px; font-weight: 600; }")
            if self._brain is not None:
                self._brain.set_mode(Mode.ULTRON)
            self._current_mode = Mode.ULTRON if AI_AVAILABLE else None
            for btn in self._mode_buttons.values():
                btn.setChecked(False)
        else:
            self.ultron_switch_btn.setText("☠ SWITCH TO ULTRON")
            self.ultron_switch_btn.setStyleSheet("")
            back = getattr(self, "_pre_ultron_mode", None) or Mode.NORMAL
            if self._brain is not None:
                self._brain.set_mode(back)
            self._current_mode = back if AI_AVAILABLE else None
            for m, btn in self._mode_buttons.items():
                btn.setChecked(m == back)
        if announce:
            self._deliver_reply("Switched back to EV." if not on else "Ultron online.")
        self._sync_corner_ui()

    def _apply_jarvis_ui(self, on: bool, announce: bool = False):
        if on:
            self._exit_style_char(silent=True)
        self._fit_to_screen()
        if on and getattr(self, "_ultron_on", False):
            self._apply_ultron_ui(False)
        if on:
            self._leave_game_karen()
        self._jarvis_on = on
        from core import voices
        voices.set_character("jarvis" if on else None)
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
        if getattr(self, "_ultron_on", False):
            self._apply_ultron_ui(False)      # picking a normal mode leaves Ultron
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
        self.observe_toggle_btn.setText("👁 EDITH: ON")
        self.observe_toggle_btn.setChecked(True)
        self._append_conversation(
            "EV", "(Edith mode on — I'll glance at your screen occasionally. "
                  "Screenshots are sent to the AI service while this is on.)"
        )
        self._observe_timer = QTimer(self)
        self._observe_timer.timeout.connect(self._maybe_observe)
        self._observe_timer.start(int(user_prefs.get("observe_interval_s")) * 1000)
        self._maybe_observe()  # don't wait a full interval for the first check
        self._sync_corner_ui()

    def _stop_observation(self):
        self._observing = False
        self.observe_toggle_btn.setText("👁 EDITH: OFF")
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
        self._refresh_face()
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
                self._hud_overlay.mode_picker_requested.connect(self._open_mode_picker)
                self._hud_overlay.tool_requested.connect(self._on_mode_tool)
            self._hud_overlay.set_state(self._state)
            mode_is_hud_mode = self._current_mode and self._current_mode.uses_hud_overlay
            self._hud_overlay.set_mode_label(
                f"{self._current_mode.label} MODE" if mode_is_hud_mode else "OBSERVING"
            )
            self._hud_overlay.set_mic_active(
                self._listener_thread is not None and self._listener_thread.isRunning()
            )
            self._hud_overlay.set_video_active(self._video_mode_on)
            self._push_mode_tools()
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
            self._restore_after_player()
        else:
            self._start_video_mode()

    def _start_video_mode(self):
        self._video_mode_on = True
        self.video_toggle_btn.setText("🎥 MINORITY: ON")
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
        self._shrink_for_player()

    def release_camera(self) -> bool:
        """Free the webcam for other apps. Returns True if EV AI was using it."""
        was_on = bool(self._video_mode_on or self._gesture_worker is not None)
        if was_on:
            self._stop_video_mode()
        return was_on

    def _shrink_for_player(self) -> None:
        """Minority / Sonar: the dashboard goes to the tray and only the player stays on screen."""
        self._player_hidden = True
        if self._tray.is_active():
            self.hide()
        else:
            self.showMinimized()

    def _restore_after_player(self) -> None:
        if getattr(self, "_player_hidden", False) and not self._video_mode_on and self._song_panel is None:
            self._player_hidden = False
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _on_video_view_closed(self):
        # The person closed the camera window: that means "turn Video mode off".
        self._video_view = None
        if self._video_mode_on:
            self._stop_video_mode()
        self._restore_after_player()

    def _stop_video_mode(self):
        self._video_mode_on = False
        if self._video_view is not None:
            view, self._video_view = self._video_view, None
            try:
                view.closed.disconnect(self._on_video_view_closed)
            except (TypeError, RuntimeError):
                pass
            view.close()
        self.video_toggle_btn.setText("🎥 MINORITY: OFF")
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
        self.song_toggle_btn.setText("🎵 SONAR: ON")
        self.song_toggle_btn.setChecked(True)
        self._shrink_for_player()

    def _on_song_panel_closed(self):
        self._song_panel = None
        self.song_toggle_btn.setText("🎵 SONAR: OFF")
        self.song_toggle_btn.setChecked(False)
        self._restore_after_player()

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
        self._cloud_sync_on_exit()
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
        if not hasattr(self, "_metrics_panel"):
            return
        now = datetime.datetime.now()
        self.time_value.setText(now.strftime("%H:%M:%S"))
        # DD-MM-YY + weekday, e.g. "12-10-26 Saturday".
        self.date_value.setText(now.strftime("%d-%m-%y %A"))

        try:
            cpu_text = f"{psutil.cpu_percent(interval=None):.0f}%"
            ram_text = f"{psutil.virtual_memory().percent:.0f}%"
        except Exception:
            # Never let a metrics failure crash the UI.
            cpu_text, ram_text = "N/A", "N/A"
        if self._hud_overlay is not None:
            self._hud_overlay.set_metrics(cpu_text, ram_text)

        # Simple internet check placeholder — a real check is added in a
        # later stage (it will avoid blocking the UI thread).
        self.internet_status_label.setText("INTERNET: (checked at startup)")
