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


class SystemMonitorPanel(QWidget):
    warning = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watch = SystemWatch()
        self._rows = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
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
            self._set("battery", bat.percent, f"{bat.percent:.0f}%{' (charging)' if plugged else ''}",
                      (not plugged) and bat.percent <= 15)
        else:
            plugged = True
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
