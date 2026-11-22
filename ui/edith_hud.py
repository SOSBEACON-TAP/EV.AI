"""
ui/edith_hud.py
-----------------
EDITH's HUD: a calm, glassy overlay for the whole screen. It is made of a few separate see-through windows so that
everything behind them stays usable:
  - edge layer: thin cyan lines along the screen edges, a soft vignette and a slim status ribbon (clicks go straight through)
  - command bar (top centre): one slim line to ask EV anything, with a few suggestions
  - context panel (left): the program in front and what is running
  - summary panel (right): the last thing EV said
  - orb (bottom right): a small pulsing core; click it to close the HUD
Original design: dark navy glass, cyan accents, no film artwork.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

CYAN = QColor(80, 220, 255)
_GLASS = ("QFrame#glass { background: rgba(8,16,32,190); border: 1px solid rgba(80,220,255,110); border-radius: 14px; }"
          "QLabel { color: #CFEFFF; background: transparent; }"
          "QLabel#h { color: #5CE1FF; font-size: 9px; letter-spacing: 2px; font-weight: bold; }"
          "QLineEdit { background: rgba(255,255,255,12); color: #E8F8FF; border: 1px solid rgba(80,220,255,90); border-radius: 10px; "
          "padding: 7px 12px; font-size: 13px; selection-background-color: #1B6E8A; }"
          "QPushButton { background: rgba(80,220,255,22); color: #BFEFFF; border: 1px solid rgba(80,220,255,80); border-radius: 9px; "
          "padding: 4px 10px; font-size: 11px; }"
          "QPushButton:hover { background: rgba(80,220,255,60); }")


def _window(widget: QWidget, click_through: bool = False) -> None:
    flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
    if click_through:
        flags |= Qt.WindowTransparentForInput
    widget.setWindowFlags(flags)
    widget.setAttribute(Qt.WA_TranslucentBackground, True)
    widget.setAttribute(Qt.WA_ShowWithoutActivating, True)


def _glass_window(title: str, width: int) -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    _window(w)
    w.setFixedWidth(width)
    outer = QVBoxLayout(w)
    outer.setContentsMargins(0, 0, 0, 0)
    f = QFrame()
    f.setObjectName("glass")
    f.setStyleSheet(_GLASS)
    outer.addWidget(f)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(6)
    h = QLabel(title)
    h.setObjectName("h")
    lay.addWidget(h)
    return w, lay


class _EdgeLayer(QWidget):
    def __init__(self):
        super().__init__()
        _window(self, click_through=True)
        self.project = "EV AI"
        self.metrics = ""
        self._t0 = time.monotonic()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        v = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.72)      # soft focus vignette
        v.setColorAt(0.0, QColor(0, 8, 20, 0))
        v.setColorAt(0.62, QColor(0, 8, 20, 0))
        v.setColorAt(1.0, QColor(0, 10, 26, 120))
        p.fillRect(self.rect(), QBrush(v))
        for (x1, y1, x2, y2) in ((6, 6, w - 6, 6), (6, h - 6, w - 6, h - 6), (6, 6, 6, h - 6), (w - 6, 6, w - 6, h - 6)):
            g = QLinearGradient(x1, y1, x2, y2)                              # thin glowing lines, brightest at the corners
            g.setColorAt(0.0, QColor(80, 220, 255, 150))
            g.setColorAt(0.5, QColor(80, 220, 255, 30))
            g.setColorAt(1.0, QColor(80, 220, 255, 150))
            p.setPen(QPen(QBrush(g), 1.2))
            p.drawLine(x1, y1, x2, y2)
        p.setPen(QPen(QColor(120, 235, 255, 200), 2))
        L = 26
        for (cx, cy, dx, dy) in ((6, 6, 1, 1), (w - 6, 6, -1, 1), (6, h - 6, 1, -1), (w - 6, h - 6, -1, -1)):
            p.drawLine(cx, cy, cx + dx * L, cy)
            p.drawLine(cx, cy, cx, cy + dy * L)
        p.fillRect(QRectF(0, 0, w, 28), QColor(6, 14, 28, 150))               # status ribbon
        p.setPen(QColor(80, 220, 255, 110))
        p.drawLine(0, 28, w, 28)
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(150, 235, 255))
        p.drawText(QRectF(16, 0, w / 3, 28), Qt.AlignVCenter | Qt.AlignLeft, "EV  ·  EDITH")
        p.drawText(QRectF(w / 3, 0, w / 3, 28), Qt.AlignCenter, (self.project or "")[:60])
        p.drawText(QRectF(w * 2 / 3, 0, w / 3 - 16, 28), Qt.AlignVCenter | Qt.AlignRight,
                   (self.metrics + "   " if self.metrics else "") + time.strftime("%H:%M"))
        p.end()


class _Orb(QWidget):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        _window(self)
        self.setFixedSize(92, 92)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("EDITH is watching. Click to close the HUD.")
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, e) -> None:  # noqa: N802
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    def _tick(self) -> None:
        self._t += 0.04
        self.update()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        pulse = 0.5 + 0.5 * math.sin(self._t * 2.0)
        g = QRadialGradient(c, 40)
        g.setColorAt(0.0, QColor(190, 245, 255, 230))
        g.setColorAt(0.35, QColor(60, 200, 245, int(150 + 60 * pulse)))
        g.setColorAt(1.0, QColor(20, 120, 200, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, 40, 40)
        p.setBrush(Qt.NoBrush)
        for i, (r, speed) in enumerate(((30, 40), (22, -60))):                 # faint rotating holographic rings
            pen = QPen(QColor(120, 235, 255, 150 - i * 40), 1.1, Qt.DashLine)
            p.setPen(pen)
            p.save()
            p.translate(c)
            p.rotate(self._t * speed)
            p.drawEllipse(QPointF(0, 0), r, r)
            p.restore()
        p.end()


class EdithHUD(QWidget):
    """Owner of the HUD windows. Not shown itself."""
    submitted = Signal(str)
    closed = Signal()
    look_requested = Signal()

    SUGGESTIONS = ("Look at my screen now", "What am I doing?", "Summarize this page", "What should I do next?")

    def __init__(self):
        super().__init__()
        self._edge = _EdgeLayer()
        self._bar, bl = _glass_window("COMMAND", 600)
        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask EV anything…")
        self._input.returnPressed.connect(self._submit)
        row.addWidget(self._input)
        bl.addLayout(row)
        chips = QHBoxLayout()
        for s in self.SUGGESTIONS:
            b = QPushButton(s)
            b.clicked.connect(lambda _=False, t=s: self._chip(t))
            chips.addWidget(b)
        chips.addStretch(1)
        bl.addLayout(chips)

        self._left, ll = _glass_window("CONTEXT", 250)
        self._ctx_app = QLabel("—")
        self._ctx_app.setWordWrap(True)
        self._ctx_title = QLabel("")
        self._ctx_title.setWordWrap(True)
        self._ctx_title.setStyleSheet("color: #8FB8CC; font-size: 11px;")
        ll.addWidget(self._ctx_app)
        ll.addWidget(self._ctx_title)
        h = QLabel("ACTIVE")
        h.setObjectName("h")
        ll.addSpacing(8)
        ll.addWidget(h)
        self._agents = QLabel("")
        self._agents.setWordWrap(True)
        ll.addWidget(self._agents)

        self._right, rl = _glass_window("SUMMARY", 300)
        self._reply = QLabel("I'm watching your screen now and then. I'll speak up when something is worth mentioning.")
        self._reply.setWordWrap(True)
        self._reply.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._reply.setMinimumHeight(120)
        rl.addWidget(self._reply)
        look = QPushButton("Look now")
        look.clicked.connect(self.look_requested.emit)
        rl.addWidget(look)

        self._orb = _Orb()
        self._orb.clicked.connect(self.closed.emit)
        self._mic = False
        self._interval = 20
        self._last_glance = None
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._refresh)
        self._wins = [self._edge, self._left, self._right, self._bar, self._orb]

    # ---- public ----
    def set_reply(self, text: str) -> None:
        self._reply.setText(str(text)[:900])

    def set_status(self, mic_on: bool, interval_s: int) -> None:
        self._mic, self._interval = mic_on, interval_s
        self._refresh_agents()

    def note_glance(self) -> None:
        self._last_glance = time.time()
        self._refresh_agents()

    def show_hud(self) -> None:
        scr = QGuiApplication.primaryScreen().geometry()
        self._edge.setGeometry(scr)
        self._left.adjustSize()
        self._right.adjustSize()
        self._bar.adjustSize()
        self._left.move(scr.left() + 28, scr.top() + 90)
        self._right.move(scr.right() - self._right.width() - 28, scr.top() + 90)
        self._bar.move(scr.center().x() - self._bar.width() // 2, scr.top() + 44)
        self._orb.move(scr.right() - 92 - 28, scr.bottom() - 92 - 28)
        for w in self._wins:
            w.show()
        self._bar.raise_()
        self._refresh()
        self._timer.start()

    def hide_hud(self) -> None:
        self._timer.stop()
        for w in self._wins:
            w.hide()

    # ---- internals ----
    def _submit(self) -> None:
        t = self._input.text().strip()
        if t:
            self._input.clear()
            self.submitted.emit(t)

    def _chip(self, text: str) -> None:
        if text == "Look at my screen now":
            self.look_requested.emit()
        else:
            self.submitted.emit(text)

    def _refresh_agents(self) -> None:
        glance = "never yet" if self._last_glance is None else f"{int(time.time() - self._last_glance)} s ago"
        self._agents.setText(f"●  Screen watcher: every {self._interval} s (last look {glance})\n"
                             f"{'●' if self._mic else '○'}  Voice: {'listening' if self._mic else 'off'}\n●  Mode: EDITH")

    def _refresh(self) -> None:
        try:
            from core.focus_match import active_window
            win = active_window()
            if win:
                prog = (win[2] or "").replace(".exe", "").title()
                title = win[1] or ""
                self._ctx_app.setText(prog or "—")
                self._ctx_title.setText(title[:80])
                self._edge.project = title[:60] or prog or "EV AI"
        except Exception:
            pass
        try:
            import psutil
            self._edge.metrics = f"CPU {int(psutil.cpu_percent())}%   RAM {int(psutil.virtual_memory().percent)}%"
        except Exception:
            self._edge.metrics = ""
        self._edge.update()
        self._refresh_agents()
