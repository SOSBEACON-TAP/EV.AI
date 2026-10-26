"""
ui/hud_overlay.py
--------------------
The HUD overlay — shown instead of the full dashboard during Automatic
mode, Serious mode, Study mode, or Observation mode (see
ui/main_window.py's _sync_corner_ui).

Three small top-level widgets work together:
- _HUDToggleButton: a tiny always-on-top corner button. This is what you
  see first when a HUD mode turns on — click it to pop the full HUD out.
- _ClickThroughBackdrop: a full-screen dim layer behind the panel, with
  mouse input disabled entirely, so whatever app is behind EV AI stays
  fully clickable while the HUD is up.
- HUDOverlayWidget itself: the actual glass-panel content column (status,
  hologram core, waveform, response, system monitoring, quick-launch
  buttons, recent commands, mic/stop/input controls). It's a normal
  (non click-through) floating window, fixed-width, centered on screen —
  not full screen — so there's always desktop visible, and clickable,
  around it.

A minimize button next to the close button collapses the panel + backdrop
back down to just the toggle button, without leaving the HUD mode
entirely (that's still what the close button does, via restore_requested).

Original design only: dark translucent glass panels, thin cyan/blue glow
lines, the existing AICoreWidget ring as the central "hologram" (no eye
imagery, per the project's own design rule), and a simple animated bar
waveform. Nothing here reproduces any specific film's UI — it's a generic
sci-fi HUD aesthetic (dark background + cyan glow + glass panels), which
isn't anyone's protected design.
"""

import math

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QFrame,
)

from config import settings
from core.state import AIState
from ui.animations import AICoreWidget


def _glass(accent_rgba="12,22,34,205"):
    # Solid-reading dark glass panel with a cyan glow edge (alpha 205/255),
    # not a near-invisible tint.
    return (
        f"background: rgba({accent_rgba}); "
        "border: 1px solid rgba(120,190,255,110); border-radius: 8px;"
    )


class _WaveformWidget(QWidget):
    """A small animated bar waveform — taller/faster bars while EV is
    listening or speaking, a slow idle ripple otherwise."""

    BAR_COUNT = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._phase = 0.0
        self._active = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_active(self, active: bool) -> None:
        self._active = active

    def _tick(self):
        self._phase += 0.35 if self._active else 0.08
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            bar_w = w / self.BAR_COUNT
            color = QColor(110, 200, 255)
            for i in range(self.BAR_COUNT):
                amp = 0.5 + 0.5 * math.sin(self._phase + i * 0.6)
                scale = 0.85 if self._active else 0.25
                bar_h = max(3, amp * h * scale)
                x = i * bar_w + bar_w * 0.25
                y = (h - bar_h) / 2
                c = QColor(color)
                c.setAlpha(220 if self._active else 110)
                painter.setPen(Qt.NoPen)
                painter.setBrush(c)
                painter.drawRoundedRect(int(x), int(y), int(bar_w * 0.5), int(bar_h), 2, 2)
        finally:
            # See AICoreWidget.paintEvent in ui/animations.py for why this
            # must always run, even if the loop above raises.
            painter.end()


class _ClickThroughBackdrop(QWidget):
    """Full-screen dim layer behind the HUD panel. WA_TransparentForMouseEvents
    plus the WindowTransparentForInput flag make the whole thing click-through
    at the OS level, so apps behind EV AI stay fully usable while the HUD is
    up — only the panel itself (a separate widget) actually receives clicks."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(4, 8, 14, 150))
        finally:
            painter.end()

    def fill_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())


class _HUDToggleButton(QPushButton):
    """Tiny always-on-top corner button shown whenever a HUD mode is active
    but the full panel is collapsed. Click it to pop the HUD panel out."""

    def __init__(self):
        super().__init__("EV")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(52, 52)
        self.setToolTip(f"Open {settings.APP_NAME} HUD")
        self.setStyleSheet(
            "QPushButton { background: rgba(10,18,28,235); color: #8fd0ff; "
            "border: 2px solid rgba(120,190,255,170); border-radius: 26px; "
            "font-size: 11px; font-weight: 700; letter-spacing: 1px; }"
            "QPushButton:hover { background: rgba(30,55,80,235); }"
        )

    def place_top_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        margin = 24
        self.move(geo.right() - self.width() - margin, geo.top() + margin)


class _VideoPreview(QWidget):
    """Plain live-camera preview surface for the left-side video panel —
    just draws whatever QImage it was last given, scaled to fit. No
    scanning sweep or lock-on geometry here (that's StartupScreen's
    _FaceScanWidget, for the auth step only); this is a live feed while
    Video mode is running."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 165)
        self._pixmap = None

    def set_frame(self, qimage) -> None:
        self._pixmap = QPixmap.fromImage(qimage)
        self.update()

    def clear_frame(self) -> None:
        self._pixmap = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(4, 8, 14, 230))
            painter.drawRoundedRect(self.rect(), 8, 8)
            if self._pixmap is not None and not self._pixmap.isNull():
                scaled = self._pixmap.scaled(
                    self.width(), self.height(),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                x = (self.width() - scaled.width()) // 2
                y = (self.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            else:
                painter.setPen(QColor(90, 130, 160))
                painter.drawText(self.rect(), Qt.AlignCenter, "VIDEO OFF")
        finally:
            painter.end()


class _VideoPanel(QWidget):
    """Left-side HUD panel: video-mode on/off toggle + the live camera
    preview ("viewing the video screen") while it's on. A separate
    top-level widget from the main content panel, same flag pattern, so
    it can sit on the opposite side of the screen and show/hide with the
    expanded HUD independently of the main panel's own layout."""

    toggle_clicked = Signal()

    WIDTH = 252

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(self.WIDTH)
        self._build_ui()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(6, 12, 20, 235))
            painter.drawRoundedRect(self.rect(), 14, 14)
        finally:
            painter.end()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 16, 14, 16)
        root.setSpacing(10)

        title = QLabel("VIDEO MODE")
        title.setStyleSheet("color: #bfe6ff; font-size: 12px; font-weight: 600; letter-spacing: 2px;")
        root.addWidget(title)

        frame = QFrame()
        frame.setStyleSheet(_glass())
        frame_layout = QVBoxLayout(frame)
        frame_layout.setSpacing(8)

        self.preview = _VideoPreview()
        self.preview.setVisible(False)   # the live camera now has its own small window (ui/video_view.py)
        frame_layout.addWidget(self.preview, alignment=Qt.AlignCenter)

        self.status_label = QLabel("Video mode is off")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #8fd0ff; font-size: 10px;")
        frame_layout.addWidget(self.status_label)

        self.toggle_btn = QPushButton("🤚 VIDEO: OFF")
        self.toggle_btn.setFixedHeight(30)
        self.toggle_btn.setStyleSheet(
            "QPushButton { background: rgba(100,180,255,25); color: #bfe6ff; "
            "border: 1px solid rgba(120,190,255,70); border-radius: 6px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(100,180,255,55); }"
        )
        self.toggle_btn.clicked.connect(self.toggle_clicked.emit)
        frame_layout.addWidget(self.toggle_btn)

        root.addWidget(frame)

    # -- public API -----------------------------------------------------
    def set_active(self, active: bool) -> None:
        self.toggle_btn.setText("🤚 VIDEO: ON" if active else "🤚 VIDEO: OFF")
        if not active:
            self.preview.clear_frame()
            self.status_label.setText("Video mode is off")

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_frame(self, qimage) -> None:
        self.preview.set_frame(qimage)


class HUDOverlayWidget(QWidget):
    text_submitted = Signal(str)
    restore_requested = Signal()
    quick_action_requested = Signal(str)
    mic_toggle_requested = Signal()
    stop_requested = Signal()
    video_toggle_requested = Signal()

    CONTENT_WIDTH = 330

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(self.CONTENT_WIDTH)

        self._expanded = False
        self._backdrop = _ClickThroughBackdrop()
        self._toggle = _HUDToggleButton()
        self._toggle.clicked.connect(self._expand)

        self._video_panel = _VideoPanel()
        self._video_panel.toggle_clicked.connect(self.video_toggle_requested.emit)

        self._build_ui()

    def paintEvent(self, event):
        # Solid rounded glass background behind the content column. The
        # panel itself is sized to its content (not the whole screen) —
        # the separate click-through backdrop widget handles dimming the
        # rest of the desktop, so this window never blocks clicks outside
        # its own bounds.
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(6, 12, 20, 235))
            painter.drawRoundedRect(self.rect(), 14, 14)
        finally:
            painter.end()

    # -- layout -----------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 18, 16, 18)
        root.setSpacing(10)

        # Header: name + status + minimize + close
        header = QHBoxLayout()
        title = QLabel(settings.APP_NAME)
        title.setStyleSheet("color: #bfe6ff; font-size: 15px; font-weight: 600; letter-spacing: 2px;")
        header.addWidget(title)
        self.status_label = QLabel("● MODE ACTIVE")
        self.status_label.setStyleSheet("color: #58d6a0; font-size: 10px;")
        header.addWidget(self.status_label)
        header.addStretch(1)

        def _header_btn(symbol, tooltip):
            b = QPushButton(symbol)
            b.setFixedSize(22, 22)
            b.setToolTip(tooltip)
            b.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,20); color: white; "
                "border: none; border-radius: 11px; font-size: 12px; }"
                "QPushButton:hover { background: rgba(255,255,255,55); }"
            )
            return b

        video_btn = _header_btn("🎥", "Turn Video mode on / off")
        video_btn.clicked.connect(self.video_toggle_requested.emit)
        header.addWidget(video_btn)

        minimize_btn = _header_btn("—", "Shrink (stay in this mode)")
        minimize_btn.clicked.connect(self._collapse)
        header.addWidget(minimize_btn)

        close_btn = _header_btn("✕", "Close (exit this mode)")
        close_btn.clicked.connect(self.restore_requested.emit)
        header.addWidget(close_btn)
        root.addLayout(header)

        # Central hologram core
        core_frame = QFrame()
        core_frame.setStyleSheet(_glass())
        core_layout = QVBoxLayout(core_frame)
        self.ring = AICoreWidget()
        self.ring.setFixedSize(150, 150)
        core_layout.addWidget(self.ring, alignment=Qt.AlignCenter)
        self.state_caption = QLabel(AIState.IDLE.label)
        self.state_caption.setAlignment(Qt.AlignCenter)
        self.state_caption.setStyleSheet("color: #8fd0ff; font-size: 10px; letter-spacing: 1px;")
        core_layout.addWidget(self.state_caption)
        root.addWidget(core_frame)

        # Voice waveform
        wave_frame = QFrame()
        wave_frame.setStyleSheet(_glass())
        wave_layout = QVBoxLayout(wave_frame)
        wave_label = QLabel("VOICE")
        wave_label.setStyleSheet("color: #6fb8e8; font-size: 9px; letter-spacing: 1px;")
        wave_layout.addWidget(wave_label)
        self.waveform = _WaveformWidget()
        wave_layout.addWidget(self.waveform)
        root.addWidget(wave_frame)

        # AI response panel
        response_frame = QFrame()
        response_frame.setStyleSheet(_glass())
        response_layout = QVBoxLayout(response_frame)
        response_label = QLabel("RESPONSE")
        response_label.setStyleSheet("color: #6fb8e8; font-size: 9px; letter-spacing: 1px;")
        response_layout.addWidget(response_label)
        self.response_view = QTextEdit()
        self.response_view.setReadOnly(True)
        self.response_view.setFixedHeight(80)
        self.response_view.setStyleSheet(
            "background: transparent; color: #d8eeff; border: none; font-size: 11px;"
        )
        response_layout.addWidget(self.response_view)
        root.addWidget(response_frame)

        # System monitoring
        sys_frame = QFrame()
        sys_frame.setStyleSheet(_glass())
        sys_layout = QHBoxLayout(sys_frame)
        self.cpu_label = QLabel("CPU --%")
        self.ram_label = QLabel("RAM --%")
        for lbl in (self.cpu_label, self.ram_label):
            lbl.setStyleSheet("color: #8fd0ff; font-size: 10px;")
            sys_layout.addWidget(lbl)
        root.addWidget(sys_frame)

        # Quick-launch buttons
        quick_frame = QFrame()
        quick_frame.setStyleSheet(_glass())
        quick_layout = QHBoxLayout(quick_frame)
        quick_defs = [
            ("YT", "open youtube"),
            ("WA", "open whatsapp web"),
            ("WEB", "open chrome"),
            ("NOTE", "open notepad"),
        ]
        for label, command in quick_defs:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setStyleSheet(
                "QPushButton { background: rgba(100,180,255,25); color: #bfe6ff; "
                "border: 1px solid rgba(120,190,255,70); border-radius: 5px; font-size: 10px; }"
                "QPushButton:hover { background: rgba(100,180,255,55); }"
            )
            btn.clicked.connect(lambda _, c=command: self.quick_action_requested.emit(c))
            quick_layout.addWidget(btn)
        root.addWidget(quick_frame)

        # Recent commands
        recent_frame = QFrame()
        recent_frame.setStyleSheet(_glass())
        recent_layout = QVBoxLayout(recent_frame)
        recent_label = QLabel("RECENT")
        recent_label.setStyleSheet("color: #6fb8e8; font-size: 9px; letter-spacing: 1px;")
        recent_layout.addWidget(recent_label)
        self.recent_label = QLabel("—")
        self.recent_label.setWordWrap(True)
        self.recent_label.setStyleSheet("color: #a8c8e0; font-size: 10px;")
        recent_layout.addWidget(self.recent_label)
        root.addWidget(recent_frame)

        # Mic / speaker controls + input
        controls = QHBoxLayout()
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(30, 30)
        self.mic_btn.setToolTip("Start/stop voice listening")
        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(30, 30)
        self.stop_btn.setToolTip("Stop/interrupt EV")
        for b in (self.mic_btn, self.stop_btn):
            b.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,15); color: #d8eeff; "
                "border: 1px solid rgba(120,190,255,60); border-radius: 15px; }"
                "QPushButton:hover { background: rgba(255,255,255,40); }"
            )
        self.mic_btn.clicked.connect(self.mic_toggle_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        controls.addWidget(self.mic_btn)
        controls.addWidget(self.stop_btn)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask EV...")
        self.input_box.setStyleSheet(
            "QLineEdit { background: rgba(10,14,22,180); color: white; "
            "border: 1px solid rgba(120,190,255,60); border-radius: 6px; "
            "padding: 4px 6px; font-size: 11px; }"
        )
        self.input_box.returnPressed.connect(self._on_submit)
        controls.addWidget(self.input_box, 1)
        root.addLayout(controls)

    # -- public API -----------------------------------------------------
    def set_mode_label(self, text: str) -> None:
        self.status_label.setText(f"● {text}")

    def set_state(self, state: AIState) -> None:
        self.ring.set_state(state)
        self.state_caption.setText(state.label)
        self.waveform.set_active(state in (AIState.LISTENING, AIState.SPEAKING))

    def set_last_reply(self, text: str) -> None:
        self.response_view.setPlainText(text)

    def set_metrics(self, cpu_text: str, ram_text: str) -> None:
        self.cpu_label.setText(f"CPU {cpu_text}")
        self.ram_label.setText(f"RAM {ram_text}")

    def set_recent_commands(self, commands: list[str]) -> None:
        self.recent_label.setText("\n".join(commands) if commands else "—")

    def set_mic_active(self, active: bool) -> None:
        self.mic_btn.setText("🎤" if not active else "🔴")

    def set_video_active(self, active: bool) -> None:
        """Keeps the HUD's left-panel toggle in sync whether Video mode
        was started from here or from the main dashboard button."""
        self._video_panel.set_active(active)

    def set_video_status(self, text: str) -> None:
        self._video_panel.set_status(text)

    def set_video_frame(self, data: dict) -> None:
        qimage = data.get("qimage") if data else None
        if qimage is not None:
            self._video_panel.set_frame(qimage)

    def show_overlay(self) -> None:
        """Called whenever a HUD-using mode (or Observation) turns on.
        Doesn't force the full panel open — if already expanded, keeps it
        that way; otherwise just shows the small toggle button, per
        "before the hud comes there should be a button"."""
        if self._expanded:
            self._position_panel()
            self._position_video_panel()
            self.show()
            self.raise_()
        else:
            self._toggle.place_top_right()
            self._toggle.show()
            self._toggle.raise_()

    def hide_overlay(self) -> None:
        """Fully hides the HUD (toggle, backdrop, and panel) — used when
        the active mode/Observation turns off entirely. Compare to
        _collapse(), which only shrinks back to the toggle button while
        staying in the mode."""
        self._expanded = False
        super().hide()
        self._video_panel.hide()
        self._backdrop.hide()
        self._toggle.hide()

    def close(self):
        self._video_panel.close()
        self._backdrop.close()
        self._toggle.close()
        return super().close()

    # -- internal -----------------------------------------------------------
    def _expand(self) -> None:
        self._expanded = True
        self._toggle.hide()
        self._position_panel()
        self.show()
        self.raise_()
        self.activateWindow()

    def _collapse(self) -> None:
        self._expanded = False
        super().hide()
        self._video_panel.hide()
        self._backdrop.hide()
        self._toggle.place_top_right()
        self._toggle.show()
        self._toggle.raise_()

    def _position_panel(self) -> None:
        # Compact HUD: small window in the bottom-right corner (no full-screen dimming).
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        self.adjustSize()
        geo = screen.availableGeometry()
        margin = 28
        x = geo.right() - self.width() - margin
        y = geo.bottom() - self.height() - margin
        self.move(x, y)

    def _position_video_panel(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        self._video_panel.adjustSize()
        geo = screen.availableGeometry()
        margin = 28
        x = geo.left() + margin
        y = geo.center().y() - self._video_panel.height() // 2
        self._video_panel.move(x, y)

    def _on_submit(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self.text_submitted.emit(text)
