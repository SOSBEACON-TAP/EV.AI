"""
ui/startup_screen.py
---------------------
Stage 10: the window EV AI shows while it's starting up, before the
main window appears. Always shows a progress bar; when
FACE_AUTH_ENABLED=true in .env it also runs the webcam owner check here
(core/face_auth.verify_owner) — with a live camera preview and a
scanning-line/ring overlay — so a stranger never even sees the main
window, instead of it opening and being checked afterward.

The actual work happens on a background QThread (_StartupWorker) so the
progress bar and camera preview animate smoothly instead of freezing
while the webcam opens and OpenCV runs — Qt's own event loop can't
paint while Python code is blocking the main thread. Camera frames are
handed back to the GUI thread via a Qt signal (frame_ready), never
touched directly from the worker thread, since Qt widgets aren't
thread-safe.
"""

import random
import time

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRectF, QPointF
from PySide6.QtGui import QGuiApplication, QColor, QPainter, QPen, QImage, QPixmap, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QProgressBar,
)

from config import settings
from core.face_auth import has_password_set, verify_password

# Purely cosmetic — cycled underneath the real status line while
# something is happening, for the sci-fi "systems coming online" feel
# the user asked for. Never used in place of the real status text,
# which always reflects what's actually going on (settings loading,
# looking for you, etc.).
_FLAVOR_PHRASES = [
    "Establishing satellite uplink...",
    "Calibrating optical sensors...",
    "Syncing neural core...",
    "Warming up the mainframe...",
    "Aligning biometric array...",
    "Initializing EV protocols...",
    "Decrypting local systems...",
    "Spinning up subsystems...",
]


class _StartupWorker(QThread):
    progress = Signal(int, str)      # percent, status text
    frame_ready = Signal(object)     # dict: qimage, frame_size, face_rect, matched
    finished_ok = Signal()
    finished_denied = Signal(str)    # reason shown to the user

    _PREVIEW_INTERVAL = 0.08  # ~12 fps cap on the camera preview — plenty smooth to
    # watch, but the webcam itself captures faster than that, and emitting every
    # single frame flooded the GUI thread with repaints, which starved the
    # progress bar's own timer and made it look like it "jumped" instead of
    # easing — this throttle is what fixes that.

    def run(self) -> None:
        print(f"[EV AI] Startup: FACE_AUTH_ENABLED={settings.FACE_AUTH_ENABLED}")
        self._last_frame_emit = 0.0
        self._last_progress_emit = 0.0
        self.progress.emit(10, "Loading configuration...")

        if settings.FACE_AUTH_ENABLED:
            self.progress.emit(25, "Looking for you...")
            self._scan_start = time.time()
            # Pacing is based on a short, fixed reference (not the full
            # FACE_AUTH_TIMEOUT, which can be 8+ seconds) — recognizing
            # you quickly should look quick, not crawl toward 80% as if
            # the whole timeout budget were expected to be used. If a
            # scan genuinely runs long, this just means the bar reaches
            # ~80% fast and sits there until a match (or the real
            # timeout) ends it — it never races ahead of the real check.
            self._scan_pace_reference = 1.6
            from core.face_auth import verify_owner
            ok, reason = verify_owner(frame_callback=self._on_frame)
            print(f"[EV AI] Startup: face check result ok={ok} reason={reason!r}")
            if not ok:
                self.finished_denied.emit(reason or "Face not recognized.")
                return
            self.progress.emit(90, "Welcome back.")
            self.msleep(120)  # bare minimum so 90% is visible before the final step
        else:
            self.progress.emit(60, "Starting up...")

        self.progress.emit(100, "Ready.")
        self.finished_ok.emit()

    def _on_frame(self, frame_bgr, face_rect, matched) -> None:
        """Called by core.face_auth.verify_owner once per captured frame
        (from this worker thread). Converts to a QImage and hands it to
        the GUI thread via a signal — never touch widgets directly here.
        Throttled to _PREVIEW_INTERVAL, except the frame that actually
        confirms a match is always sent through so the green "locked on"
        state never gets dropped.

        Also nudges the progress bar forward based on real elapsed
        scanning time (25% up to ~80%) — without this the bar sat flat
        at 25% for however long scanning took, then jumped straight to
        100% at the very end, which read as broken rather than "slow"."""
        now = time.time()
        if not matched and (now - self._last_progress_emit) >= 0.1:
            self._last_progress_emit = now
            elapsed_fraction = min(1.0, (now - self._scan_start) / self._scan_pace_reference)
            self.progress.emit(int(25 + elapsed_fraction * 55), "Looking for you...")

        if not matched and (now - self._last_frame_emit) < self._PREVIEW_INTERVAL:
            return
        self._last_frame_emit = now
        try:
            import cv2
            h, w = frame_bgr.shape[:2]
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            qimage = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy()
            self.frame_ready.emit({
                "qimage": qimage,
                "frame_size": (w, h),
                "face_rect": face_rect,
                "matched": matched,
            })
        except Exception:
            pass  # a preview hiccup should never interrupt the actual check


class _FaceScanWidget(QWidget):
    """Live camera preview with an animated red scanning line and a
    circle drawn around whatever face is currently detected — green once
    it's confirmed as the enrolled owner."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(260, 260)
        self._pixmap: QPixmap | None = None
        self._frame_size = (1, 1)
        self._face_rect = None  # (x, y, w, h) in frame-pixel coords
        self._matched = False
        self._scan_pos = 0.0
        self._scan_dir = 1
        self._lock_rotation = 0.0  # degrees — spins the "verified" geometry once matched

        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._advance_scan)
        self._scan_timer.start(25)

    def _advance_scan(self) -> None:
        self._scan_pos += 0.018 * self._scan_dir
        if self._matched:
            self._lock_rotation = (self._lock_rotation + 2.2) % 360
        if self._scan_pos >= 1.0:
            self._scan_pos, self._scan_dir = 1.0, -1
        elif self._scan_pos <= 0.0:
            self._scan_pos, self._scan_dir = 0.0, 1
        self.update()

    def _draw_lock_geometry(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        """Replaces the plain searching circle with a "verified" reticle
        once a face is matched: four corner brackets (like a camera
        autofocus box) around the face, plus a slowly spinning diamond
        at the center — a geometric lock-on marker instead of your face
        just sitting there unmarked."""
        green = QColor(70, 230, 140, 235)
        bracket_len = radius * 0.5
        box = radius * 0.95

        pen = QPen(green)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            corner_x = cx + sx * box
            corner_y = cy + sy * box
            painter.drawLine(QPointF(corner_x, corner_y), QPointF(corner_x - sx * bracket_len, corner_y))
            painter.drawLine(QPointF(corner_x, corner_y), QPointF(corner_x, corner_y - sy * bracket_len))

        painter.save()
        try:
            painter.translate(cx, cy)
            painter.rotate(self._lock_rotation)
            diamond = radius * 0.4
            pen = QPen(green)
            pen.setWidth(2)
            painter.setPen(pen)
            points = [QPointF(0, -diamond), QPointF(diamond, 0), QPointF(0, diamond), QPointF(-diamond, 0)]
            for i in range(4):
                painter.drawLine(points[i], points[(i + 1) % 4])
        finally:
            painter.restore()

    def set_frame(self, data: dict) -> None:
        self._pixmap = QPixmap.fromImage(data["qimage"])
        self._frame_size = data["frame_size"]
        self._face_rect = data["face_rect"]
        self._matched = data["matched"]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            rect = self.rect()

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(6, 12, 20, 255))
            painter.drawRoundedRect(rect, 16, 16)

            if self._pixmap is not None and not self._pixmap.isNull():
                scaled = self._pixmap.scaled(
                    rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                x = (rect.width() - scaled.width()) // 2
                y = (rect.height() - scaled.height()) // 2
                clip = QPainterPath()
                clip.addRoundedRect(QRectF(rect), 16, 16)
                painter.setClipPath(clip)
                painter.drawPixmap(x, y, scaled)
                painter.setClipping(False)

                if self._face_rect is not None:
                    frame_w, frame_h = self._frame_size
                    scale = max(rect.width() / frame_w, rect.height() / frame_h)
                    off_x = (rect.width() - frame_w * scale) / 2
                    off_y = (rect.height() - frame_h * scale) / 2
                    fx, fy, fw, fh = self._face_rect
                    cx = off_x + (fx + fw / 2) * scale
                    cy = off_y + (fy + fh / 2) * scale
                    radius = max(fw, fh) / 2 * scale * 1.2

                    if self._matched:
                        self._draw_lock_geometry(painter, cx, cy, radius)
                    else:
                        pen = QPen(QColor(255, 60, 60, 220))
                        pen.setWidth(3)
                        painter.setPen(pen)
                        painter.setBrush(Qt.NoBrush)
                        painter.drawEllipse(QPointF(cx, cy), radius, radius)
            else:
                painter.setPen(QColor(90, 110, 130))
                painter.drawText(rect, Qt.AlignCenter, "Starting camera...")

            # Animated scanning sweep line, always running — gives the
            # "actively scanning" read even on frames with no face yet.
            sweep_color = QColor(70, 230, 140, 200) if self._matched else QColor(255, 60, 60, 190)
            pen = QPen(sweep_color)
            pen.setWidth(2)
            painter.setPen(pen)
            scan_y = rect.top() + self._scan_pos * rect.height()
            painter.drawLine(rect.left() + 6, int(scan_y), rect.right() - 6, int(scan_y))
            glow = QColor(sweep_color)
            glow.setAlpha(40)
            painter.fillRect(QRectF(rect.left(), scan_y - 12, rect.width(), 24), glow)

            pen = QPen(QColor(58, 160, 255, 170))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 16, 16)
        finally:
            painter.end()


class StartupScreen(QWidget):
    """Frameless, centered splash shown before MainWindow. Call start()
    with callbacks for the two outcomes; the screen closes itself either
    way before calling back."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._show_face_scan = settings.FACE_AUTH_ENABLED
        width = 340
        self._base_height = 430 if self._show_face_scan else 170
        self._password_extra_height = 118
        self.setFixedSize(width, self._base_height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)

        title = QLabel(settings.APP_NAME)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #e8f1ff; font-size: 20px; font-weight: 600; background: transparent;")
        layout.addWidget(title)

        if self._show_face_scan:
            self._face_scan = _FaceScanWidget()
            layout.addWidget(self._face_scan, alignment=Qt.AlignCenter)
        else:
            self._face_scan = None

        self._status = QLabel("Starting up...")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #e8f1ff; font-size: 13px; background: transparent;")
        layout.addWidget(self._status)

        self._flavor = QLabel(random.choice(_FLAVOR_PHRASES))
        self._flavor.setAlignment(Qt.AlignCenter)
        self._flavor.setStyleSheet("color: #6f88a3; font-size: 11px; background: transparent;")
        layout.addWidget(self._flavor)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%p%")
        self._bar.setFixedHeight(16)
        self._set_bar_color("#3aa0ff")
        layout.addWidget(self._bar)

        # Password fallback — hidden until a face check actually fails
        # (or the camera isn't usable) and a password has been set via
        # scripts/set_password.py. Never shown in place of the face
        # check, only after it's been tried and didn't work, so a
        # stranger can't just skip the scan.
        self._password_row = QWidget()
        pw_layout = QVBoxLayout(self._password_row)
        pw_layout.setContentsMargins(0, 6, 0, 0)
        pw_layout.setSpacing(6)

        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.Password)
        self._password_input.setPlaceholderText("Password")
        self._password_input.setStyleSheet(
            "QLineEdit { background: rgba(10,14,22,220); color: white; "
            "border: 1px solid rgba(120,190,255,90); border-radius: 6px; "
            "padding: 6px 8px; font-size: 12px; }"
        )
        self._password_input.returnPressed.connect(self._submit_password)
        pw_layout.addWidget(self._password_input)

        pw_btn_row = QHBoxLayout()
        self._unlock_btn = QPushButton("Unlock")
        self._unlock_btn.clicked.connect(self._submit_password)
        self._quit_btn = QPushButton("Quit")
        self._quit_btn.clicked.connect(self._finish_denied)
        for btn in (self._unlock_btn, self._quit_btn):
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                "QPushButton { background: rgba(100,180,255,30); color: #bfe6ff; "
                "border: 1px solid rgba(120,190,255,80); border-radius: 6px; font-size: 11px; }"
                "QPushButton:hover { background: rgba(100,180,255,60); }"
                "QPushButton:disabled { color: #566879; background: rgba(100,180,255,10); }"
            )
            pw_btn_row.addWidget(btn)
        pw_layout.addLayout(pw_btn_row)

        self._password_error = QLabel("")
        self._password_error.setAlignment(Qt.AlignCenter)
        self._password_error.setWordWrap(True)
        self._password_error.setStyleSheet("color: #ff8a8a; font-size: 10px; background: transparent;")
        pw_layout.addWidget(self._password_error)

        layout.addWidget(self._password_row)
        self._password_row.setVisible(False)
        self._password_attempts = 0
        self._max_password_attempts = 5

        # The worker reports discrete milestones (10%, 25%, 100%, ...);
        # this timer eases the displayed value toward the latest one
        # smoothly instead of snapping, which is what makes the bar read
        # as "a little slower" rather than instant jumps.
        self._displayed_percent = 0.0
        self._target_percent = 0
        self._closing_requested = False
        self._close_scheduled = False
        self._ease_timer = QTimer(self)
        self._ease_timer.timeout.connect(self._ease_progress)
        self._ease_timer.start(16)

        self._flavor_timer = QTimer(self)
        self._flavor_timer.timeout.connect(self._rotate_flavor)
        self._flavor_timer.start(1100)

        self._worker = _StartupWorker()
        self._worker.progress.connect(self._on_progress)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_denied.connect(self._on_denied)

        self._on_ok_callback = None
        self._on_denied_callback = None
        self._deny_reason = ""

        # Always-available close button (top-right) plus Esc — closing
        # here just quits EV.AI, it never lets anyone past the face check,
        # so it's safe to offer at any point. Added after a startup that
        # hung with no way out.
        self._close_btn = QPushButton("✕", self)
        self._close_btn.setFixedSize(26, 26)
        self._close_btn.setToolTip("Close (Esc)")
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,18); color: #e8f1ff; "
            "border: none; border-radius: 13px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(255,80,80,170); }"
        )
        self._close_btn.move(width - 26 - 12, 12)
        self._close_btn.clicked.connect(self._cancel_startup)
        self._close_btn.raise_()
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._cancel_startup()
            return
        super().keyPressEvent(event)

    def _stop_worker(self) -> None:
        """If the startup thread is still running (e.g. stuck opening a
        webcam that never answers), force it down so closing the window
        or continuing on doesn't leave a live QThread behind — Qt aborts
        the process with 'QThread: Destroyed while thread is still
        running' otherwise. terminate() is normally a last resort, but
        this only happens when we're closing anyway or the thread is
        already hung."""
        if self._worker.isRunning():
            if not self._worker.wait(1500):   # it normally ends on its own right after signalling
                self._worker.terminate()
                self._worker.wait(1000)

    def _cancel_startup(self) -> None:
        self._deny_reason = "Closed by user."
        self._stop_worker()
        self.close()
        if self._on_denied_callback:
            self._on_denied_callback(self._deny_reason)

    def _set_bar_color(self, hex_color: str) -> None:
        self._bar.setStyleSheet(
            "QProgressBar { background: #10202e; border-radius: 8px; color: #e8f1ff; "
            "font-size: 10px; font-weight: 600; }"
            f"QProgressBar::chunk {{ background: {hex_color}; border-radius: 8px; }}"
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(6, 12, 20, 240))
            painter.drawRoundedRect(self.rect(), 14, 14)
        finally:
            painter.end()

    def _center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.center().x() - self.width() // 2, geo.center().y() - self.height() // 2)

    def start(self, on_ok, on_denied) -> None:
        """Begin the startup sequence. on_ok() is called once it's safe to
        show the main window; on_denied(reason) is called instead if the
        face check failed (the caller should quit the app in that case)."""
        self._on_ok_callback = on_ok
        self._on_denied_callback = on_denied
        self._center()
        self.show()
        self._worker.start()

    def _rotate_flavor(self) -> None:
        self._flavor.setText(random.choice(_FLAVOR_PHRASES))

    def _ease_progress(self) -> None:
        if self._displayed_percent < self._target_percent:
            # Chase the target at a bounded speed (not a fixed fraction of
            # the remaining gap) so it reads as a steady, slightly slow
            # fill rather than a fast-then-crawling easing curve.
            self._displayed_percent = min(self._target_percent, self._displayed_percent + 0.6)
            self._bar.setValue(int(self._displayed_percent))

        # Once the bar has actually, visibly reached 100 (not just the
        # moment the worker said "done"), hold for a beat and close. A
        # fixed timer here previously fired before the bar had caught up
        # on a big jump, which is what looked like it "jumping" straight
        # to finished.
        if self._closing_requested and self._displayed_percent >= 100 and not self._close_scheduled:
            self._close_scheduled = True
            QTimer.singleShot(300, self._finish_ok)

    def _on_progress(self, percent: int, text: str) -> None:
        self._target_percent = percent
        self._status.setText(text)

    def _on_frame(self, data: dict) -> None:
        if self._face_scan is not None:
            self._face_scan.set_frame(data)

    def _on_ok(self) -> None:
        self._closing_requested = True

    def _finish_ok(self) -> None:
        self._stop_worker()
        self.close()
        if self._on_ok_callback:
            self._on_ok_callback()

    def _on_denied(self, reason: str) -> None:
        self._deny_reason = reason
        self._set_bar_color("#ff4d4d")
        if has_password_set():
            self._status.setText(f"Face not recognized — {reason}")
            self._show_password_prompt()
        else:
            self._status.setText(f"Access denied — {reason}")
            QTimer.singleShot(2800, self._finish_denied)

    def _show_password_prompt(self) -> None:
        if not self._password_row.isVisible():
            self._password_row.setVisible(True)
            self.setFixedHeight(self._base_height + self._password_extra_height)
            self._center()
        self._password_input.clear()
        self._password_input.setFocus()

    def _submit_password(self) -> None:
        password = self._password_input.text()
        if not password or not self._password_input.isEnabled():
            return
        if verify_password(password):
            self._password_row.setVisible(False)
            self.setFixedHeight(self._base_height)
            self._center()
            self._set_bar_color("#3aa0ff")
            self._status.setText("Welcome back.")
            self._target_percent = 100
            self._closing_requested = True
            return

        self._password_attempts += 1
        self._password_input.clear()
        remaining = self._max_password_attempts - self._password_attempts
        if remaining <= 0:
            self._password_error.setText("Too many attempts.")
            self._unlock_btn.setEnabled(False)
            self._password_input.setEnabled(False)
            QTimer.singleShot(1200, self._finish_denied)
        else:
            plural = "s" if remaining != 1 else ""
            self._password_error.setText(f"Wrong password — {remaining} attempt{plural} left.")

    def _finish_denied(self) -> None:
        self._stop_worker()
        self.close()
        if self._on_denied_callback:
            self._on_denied_callback(self._deny_reason)
