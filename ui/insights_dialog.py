"""App Usage Insights window: time per application, category totals and a
7-day trend, all from the local database (core/app_usage.py). Also holds the
privacy controls: pause tracking, exclude apps, clear history."""

from datetime import date

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from core import app_usage, user_prefs
from ui import theme as _theme
from ui.theme import dialog_stylesheet


class _HBars(QWidget):
    """Horizontal bars: label on the left, bar, value on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[str, float, str]] = []     # (label, value, value text)
        self.setMinimumHeight(40)

    def set_rows(self, rows) -> None:
        self._rows = rows
        self.setMinimumHeight(max(40, 26 * len(rows) + 8))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            hl = _theme.highlight()
            text = self.palette().color(self.foregroundRole())
            if not self._rows:
                p.setPen(text)
                p.drawText(self.rect(), Qt.AlignCenter, "Nothing recorded yet")
                return
            top = max(v for _, v, _ in self._rows) or 1.0
            label_w, value_w = 120, 70
            bar_x, bar_w = label_w + 8, max(20, self.width() - label_w - value_w - 20)
            font = QFont(self.font())
            p.setFont(font)
            for i, (label, value, shown) in enumerate(self._rows):
                y = 4 + i * 26
                p.setPen(text)
                p.drawText(QRectF(0, y, label_w, 22), Qt.AlignVCenter | Qt.AlignLeft,
                           p.fontMetrics().elidedText(label, Qt.ElideRight, label_w))
                track = QRectF(bar_x, y + 5, bar_w, 12)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(128, 150, 180, 45))
                p.drawRoundedRect(track, 6, 6)
                fill = QRectF(bar_x, y + 5, max(3.0, bar_w * value / top), 12)
                p.setBrush(hl)
                p.drawRoundedRect(fill, 6, 6)
                p.setPen(text)
                p.drawText(QRectF(bar_x + bar_w + 8, y, value_w, 22), Qt.AlignVCenter | Qt.AlignLeft, shown)
        finally:
            p.end()


class _DayBars(QWidget):
    """Seven vertical bars, one per day."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._days: list[tuple[str, float]] = []
        self.setMinimumHeight(120)

    def set_days(self, days) -> None:
        self._days = days
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            if not self._days:
                return
            hl = _theme.highlight()
            text = self.palette().color(self.foregroundRole())
            top = max(v for _, v in self._days) or 1.0
            n = len(self._days)
            slot = self.width() / n
            base = self.height() - 34
            for i, (iso, value) in enumerate(self._days):
                h = max(2.0, (base - 14) * value / top) if value > 0 else 2.0
                x = i * slot + slot * 0.2
                p.setPen(Qt.NoPen)
                p.setBrush(hl if iso == date.today().isoformat() else QColor(hl.red(), hl.green(), hl.blue(), 130))
                p.drawRoundedRect(QRectF(x, base - h, slot * 0.6, h), 4, 4)
                p.setPen(text)
                day = date.fromisoformat(iso)
                p.drawText(QRectF(i * slot, base + 4, slot, 16), Qt.AlignCenter, day.strftime("%a"))
                p.drawText(QRectF(i * slot, base + 18, slot, 14), Qt.AlignCenter,
                           app_usage.fmt_duration(value) if value else "–")
        finally:
            p.end()


class InsightsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("App Usage Insights")
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))
        self.resize(520, 640)
        root = QVBoxLayout(self)
        root.setSpacing(8)

        top = QHBoxLayout()
        self._period = QComboBox()
        for label, key in (("Today", "today"), ("Yesterday", "yesterday"),
                           ("Last 7 days", "week"), ("Last 30 days", "month")):
            self._period.addItem(label, key)
        self._period.currentIndexChanged.connect(self.refresh)
        top.addWidget(self._period)
        top.addStretch(1)
        self._total = QLabel("")
        top.addWidget(self._total)
        root.addLayout(top)

        root.addWidget(self._section("TOP APPLICATIONS"))
        self._apps = _HBars()
        root.addWidget(self._apps)
        root.addWidget(self._section("CATEGORIES"))
        self._cats = _HBars()
        root.addWidget(self._cats)
        root.addWidget(self._section("LAST 7 DAYS"))
        self._week = _DayBars()
        root.addWidget(self._week, 1)

        root.addWidget(self._section("PRIVACY"))
        self._track = QCheckBox("Track which app I'm using (stored only on this computer)")
        self._track.setChecked(user_prefs.get("usage_tracking"))
        self._track.toggled.connect(lambda on: user_prefs.set_value("usage_tracking", on))
        root.addWidget(self._track)
        ex_row = QHBoxLayout()
        ex_row.addWidget(QLabel("Never record:"))
        self._exclude = QLineEdit(user_prefs.get("usage_excluded"))
        self._exclude.setPlaceholderText("program names, e.g. discord, spotify")
        self._exclude.editingFinished.connect(
            lambda: user_prefs.set_value("usage_excluded", self._exclude.text().strip()))
        ex_row.addWidget(self._exclude, 1)
        root.addLayout(ex_row)
        btn_row = QHBoxLayout()
        clear = QPushButton("Clear all history")
        clear.clicked.connect(self._clear)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        btn_row.addWidget(clear)
        btn_row.addStretch(1)
        btn_row.addWidget(close)
        root.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(15000)
        self.refresh()

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "section")
        return label

    def refresh(self) -> None:
        period = self._period.currentData()
        apps = app_usage.app_totals(period)
        total = sum(s for _, s in apps)
        self._total.setText(f"Total: {app_usage.fmt_duration(total)}")
        self._apps.set_rows([(app_usage.friendly(a), s, app_usage.fmt_duration(s)) for a, s in apps[:8]])
        cats = app_usage.category_totals(period)
        self._cats.set_rows([(c, s, app_usage.fmt_duration(s)) for c, s in cats.items() if s > 0])
        self._week.set_days(app_usage.daily_totals(7))

    def _clear(self) -> None:
        if QMessageBox.question(self, "Clear history", "Delete all recorded app usage? This can't be undone.") \
                == QMessageBox.Yes:
            app_usage.clear_history()
            self.refresh()
