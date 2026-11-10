"""
ui/system_monitor.py
--------------------
Jarvis' live system monitor: CPU / memory / disk / battery bars that
refresh every 2 seconds while Jarvis is switched on, plus network and
uptime. Emits `warning` when something crosses a limit (see core/sysmon.py).
"""

import os
import time

import psutil
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar

from core.sysmon import SystemWatch

_BAR_QSS = (
    "QProgressBar { border: 1px solid rgba(255,196,0,90); border-radius: 4px; background: rgba(0,0,0,70); "
    "min-height: 10px; max-height: 10px; } "
    "QProgressBar::chunk { background: #FFC400; border-radius: 3px; }"
)
_BAR_WARN_QSS = _BAR_QSS.replace("#FFC400; border-radius", "#FF5252; border-radius")


class ReactorGauge(QWidget):
    """The battery as an arc reactor: glowing rings and a bright core that shows the charge, like the film prop."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self._pct = None
        self._plugged = False
        self._spin = 0.0
        self._t = QTimer(self)
        self._t.timeout.connect(self._advance)
        self._t.start(60)

    def set_value(self, pct, plugged: bool) -> None:
        self._pct, self._plugged = pct, plugged
        self.update()

    def _advance(self) -> None:
        if self.isVisible():
            self._spin = (self._spin + (3.0 if self._plugged else 1.0)) % 360
            self.update()

    def paintEvent(self, _e):  # noqa: N802
        import math
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QRadialGradient
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            r = min(w, h) / 2 - 6
            c = QPointF(w / 2, h / 2)
            pct = self._pct
            low = pct is not None and pct <= 15 and not self._plugged
            col = QColor("#FF5252") if low else QColor("#7FE9FF")
            # outer glow
            g = QRadialGradient(c, r)
            g.setColorAt(0.55, QColor(col.red(), col.green(), col.blue(), 90))
            g.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(c, r, r)
            # housing ring + the ten coil segments that spin slowly
            p.setBrush(QColor(10, 24, 30))
            p.setPen(QPen(QColor(150, 170, 180), 3))
            p.drawEllipse(c, r * 0.92, r * 0.92)
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, r * 0.78, r * 0.78)
            p.drawEllipse(c, r * 0.46, r * 0.46)
            p.setPen(QPen(col, 5))
            for i in range(10):
                a = math.radians(self._spin + i * 36)
                x1, y1 = c.x() + math.cos(a) * r * 0.5, c.y() + math.sin(a) * r * 0.5
                x2, y2 = c.x() + math.cos(a) * r * 0.74, c.y() + math.sin(a) * r * 0.74
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            # charge sweep around the outside
            if pct is not None:
                p.setPen(QPen(QColor(255, 255, 255, 230), 4))
                span = int(-360 * 16 * max(0, min(100, pct)) / 100)
                p.drawArc(int(c.x() - r * 0.86), int(c.y() - r * 0.86), int(r * 1.72), int(r * 1.72), 90 * 16, span)
            # glowing core with the number
            cg = QRadialGradient(c, r * 0.42)
            cg.setColorAt(0.0, QColor(255, 255, 255, 255))
            cg.setColorAt(0.55, QColor(col.red(), col.green(), col.blue(), 230))
            cg.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(cg))
            p.drawEllipse(c, r * 0.42, r * 0.42)
            text = "--" if pct is None else f"{pct:.0f}%"
            f = QFont("Segoe UI", max(8, int(r * 0.26)), QFont.Bold)
            p.setFont(f)
            p.setPen(QColor(6, 30, 40))
            p.drawText(self.rect(), Qt.AlignCenter, text)
            if self._plugged and pct is not None:
                p.setFont(QFont("Segoe UI", max(6, int(r * 0.1)), QFont.Bold))
                p.setPen(col)
                p.drawText(int(c.x() - r), int(c.y() + r * 0.5), int(r * 2), int(r * 0.3), Qt.AlignCenter, "CHARGING")
        finally:
            p.end()


class SystemMonitorPanel(QWidget):
    warning = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watch = SystemWatch()
        self._rows = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.reactor = ReactorGauge()
        lay.addWidget(self.reactor)
        for key, title in (("cpu", "CPU"), ("ram", "MEMORY"), ("disk", "DISK"), ("battery", "BATTERY")):
            head = QHBoxLayout()
            name = QLabel(title)
            name.setObjectName("SectionTitle")
            val = QLabel("--")
            head.addWidget(name)
            head.addStretch(1)
            head.addWidget(val)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setStyleSheet(_BAR_QSS)
            lay.addLayout(head)
            lay.addWidget(bar)
            self._rows[key] = (val, bar)
        self.net_label = QLabel("NETWORK: --")
        self.up_label = QLabel("UPTIME: --")
        lay.addWidget(self.net_label)
        lay.addWidget(self.up_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        psutil.cpu_percent(interval=None)  # prime the counter

    def start(self):
        if not self._timer.isActive():
            self._timer.start(2000)
            self._tick()

    def stop(self):
        self._timer.stop()

    def _set(self, key, pct, text, warn):
        val, bar = self._rows[key]
        val.setText(text)
        if pct is not None:
            bar.setValue(int(pct))
        bar.setStyleSheet(_BAR_WARN_QSS if warn else _BAR_QSS)

    def _tick(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            try:
                disk = psutil.disk_usage(os.path.abspath(os.sep)).percent
            except OSError:
                disk = None
            try:
                bat = psutil.sensors_battery()
            except Exception:
                bat = None
        except Exception:
            return
        self._set("cpu", cpu, f"{cpu:.0f}%", cpu >= 90)
        self._set("ram", ram, f"{ram:.0f}%", ram >= 90)
        if disk is not None:
            self._set("disk", disk, f"{disk:.0f}% used", disk >= 90)
        else:
            self._set("disk", 0, "n/a", False)
        if bat is not None:
            plugged = bool(bat.power_plugged)
            self.reactor.set_value(bat.percent, plugged)
            self._set("battery", bat.percent, f"{bat.percent:.0f}%{' (charging)' if plugged else ''}",
                      (not plugged) and bat.percent <= 15)
        else:
            plugged = True
            self.reactor.set_value(None, True)
            self._set("battery", 0, "no battery", False)
        try:
            up = [n for n, s in psutil.net_if_stats().items() if s.isup and not n.lower().startswith(("lo", "loopback"))]
            self.net_label.setText("NETWORK: " + ("connected" if up else "OFFLINE"))
        except Exception:
            self.net_label.setText("NETWORK: --")
        try:
            secs = int(time.time() - psutil.boot_time())
            self.up_label.setText(f"UPTIME: {secs // 3600}h {(secs % 3600) // 60}m")
        except Exception:
            pass
        for msg in self._watch.update(cpu, ram, disk, bat.percent if bat else None, plugged, time.time()):
            self.warning.emit(msg)
