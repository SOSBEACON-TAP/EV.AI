"""
ui/hack_terminal.py
-------------------
ULTRON's security centre, built into the Ultron screen (no pop-up):
  * HackCore        the engine: runs every check off the GUI thread and reports through signals
  * HackToolsPanel  left column: security core score + the tool buttons
  * HackRadarPanel  right column: the radar, its controls and the list of what is around you

Everything checks YOUR OWN computer, network and files, or runs educational simulations on
made-up data. The radar shows devices on your own network and the Wi-Fi networks your adapter
can hear, coloured by how well protected they are.
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime

from PySide6.QtCore import QObject, QPointF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QTextEdit,
                               QVBoxLayout, QWidget, QGridLayout, QHBoxLayout)

from core import security as sec
from ui.widgets import HoverButton

RED, DIM, BG = "#FF2A2A", "#8A1A1A", "#070001"
LEVEL_COLOR = {"ok": "#43D17A", "info": "#E0B0B0", "warn": "#FFB020", "bad": "#FF3B3B"}
LEVEL_TAG = {"ok": "[ OK ]", "info": "[ .. ]", "warn": "[WARN]", "bad": "[RISK]"}


class _Job(QThread):
    """Runs a blocking security check off the GUI thread. fn(progress) -> any object."""
    progress = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.finished_ok.emit(self._fn(self.progress.emit))
        except Exception as e:                       # never crash the app from a scan
            self.failed.emit(f"{type(e).__name__}: {e}")


class RadarWidget(QWidget):
    """Sci-fi radar. Centre = you. Circles = devices on your network. Diamonds = Wi-Fi networks around you
    (closer = stronger signal). Colour = how well protected: green good, amber weak, red open or unknown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self._angle = 0.0
        self._devices: list[dict] = []
        self._wifi: list[dict] = []
        self._view = "all"          # all | devices | wifi
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, e):       # animate only while visible (Ultron mode)
        self._timer.start(40)
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def set_data(self, devices=None, wifi=None):
        if devices is not None:
            self._devices = devices
        if wifi is not None:
            self._wifi = wifi
        self.update()

    def set_view(self, view: str):
        self._view = view
        self.update()

    def _tick(self):
        self._angle = (self._angle + 3.0) % 360
        self.update()

    @staticmethod
    def _spot(key: str, lo: float, hi: float) -> tuple[float, float]:
        h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
        return math.radians(h % 360), lo + (hi - lo) * (((h >> 9) % 100) / 100)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        c = QPointF(w / 2, h / 2)
        r = min(w, h) / 2 - 12
        p.fillRect(self.rect(), QColor(BG))
        grid = QPen(QColor(255, 42, 42, 70), 1)
        p.setPen(grid)
        for i in (1, 2, 3, 4):
            p.drawEllipse(c, r * i / 4, r * i / 4)
        p.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - r), QPointF(c.x(), c.y() + r))
        # sweep: a fading wedge behind the beam
        for i in range(40):
            a = math.radians(self._angle - i * 1.6)
            p.setPen(QPen(QColor(255, 42, 42, max(0, 110 - i * 3)), 2))
            p.drawLine(c, QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a)))
        # Wi-Fi networks: diamonds; stronger signal = nearer the centre
        for n in (self._wifi if self._view != "devices" else []):
            ang, _d = self._spot(n["ssid"] + str(n.get("channel", "")), 0, 1)
            dist = r * (0.95 - 0.8 * min(100, n["signal"]) / 100)
            x, y = c.x() + dist * math.cos(ang), c.y() - dist * math.sin(ang)
            col = QColor(LEVEL_COLOR[sec.wifi_security_level(n["auth"])])
            self._glow(p, x, y, col, ang, diamond=True)
            p.setPen(QColor(col))
            p.setFont(QFont("Consolas", 7))
            p.drawText(QPointF(x + 7, y - 6), n["ssid"][:14])
        # devices on your own network: circles
        for d in (self._devices if self._view != "wifi" else []):
            if d.get("me"):
                continue
            ang, frac = self._spot(d["ip"], 0.15, 0.55)
            x, y = c.x() + r * frac * math.cos(ang), c.y() - r * frac * math.sin(ang)
            col = QColor(LEVEL_COLOR["bad"] if d.get("unknown") else LEVEL_COLOR["ok"])
            self._glow(p, x, y, col, ang)
            p.setPen(QColor(col))
            p.setFont(QFont("Consolas", 7))
            p.drawText(QPointF(x + 7, y - 6), d["ip"])
        # you
        p.setBrush(QColor(RED))
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, 5, 5)
        p.setPen(QColor(RED))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        p.drawText(QPointF(c.x() + 8, c.y() + 14), "YOU")
        p.setPen(QPen(QColor(RED), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)

    def _glow(self, p: QPainter, x: float, y: float, col: QColor, ang: float, diamond: bool = False):
        # blips flare when the sweep beam passes over them
        diff = (self._angle - math.degrees(ang)) % 360
        bright = 255 if diff < 40 else 150
        col = QColor(col)
        col.setAlpha(bright)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        if diamond:
            p.drawPolygon([QPointF(x, y - 5), QPointF(x + 5, y), QPointF(x, y + 5), QPointF(x - 5, y)])
        else:
            p.drawEllipse(QPointF(x, y), 4, 4)


class HackCore(QObject):
    """The security engine. Output goes out through signals so any screen can show it."""
    line = Signal(str, str)            # text, level (ok/info/warn/bad)
    say = Signal(str)                  # something worth saying aloud (short)
    score_changed = Signal(int)
    radar_data = Signal(object, object, str)   # devices, wifi, my_ip
    alerts_changed = Signal(int)
    busy = Signal(str)                 # what is running now, "" when idle

    def __init__(self, parent_widget: QWidget):
        super().__init__(parent_widget)
        self.w = parent_widget
        self._jobs: list[_Job] = []
        self.findings: list[dict] = []
        self.extra_alerts: list[dict] = []
        self.devices: list[dict] = []
        self.wifi: list[dict] = []
        self._brain = None
        self._typing: list[str] = []
        self._typer = QTimer(self)
        self._typer.timeout.connect(self._type_next)

    # -------------------------------------------------------------- output
    def _line(self, text: str, level: str = "info"):
        self.line.emit(text, level)

    def _show(self, findings: list[dict]):
        for f in findings:
            self._line(f"{LEVEL_TAG[f['level']]} {f['text']}", f["level"])

    def _set_score(self):
        self.score_changed.emit(sec.score(self.findings))
        self.alerts_changed.emit(len(self.alerts()))

    def alerts(self) -> list[dict]:
        return [f for f in self.findings + self.extra_alerts if f["level"] in ("warn", "bad")]

    def _run(self, label: str, fn, on_done):
        self.busy.emit(label)
        self._line(f"[SCAN] {label} started", "info")
        job = _Job(fn, self)
        job.progress.connect(lambda t: self._line(f"[SCAN] {t}", "info"))
        job.failed.connect(lambda e: (self._line(f"[ERROR] {e}", "bad"), self.busy.emit("")))
        job.finished_ok.connect(lambda r: (on_done(r), self.busy.emit("")))
        job.finished.connect(lambda: self._jobs.remove(job) if job in self._jobs else None)
        self._jobs.append(job)
        job.start()

    # ------------------------------------------------------------- actions
    def dark_scan(self):
        def done(findings):
            self.findings = findings
            self._show(findings)
            self._set_score()
            bad = sum(f["level"] == "bad" for f in findings)
            warn = sum(f["level"] == "warn" for f in findings)
            self._line(f"[DARK SCAN] Complete: {bad} risk(s), {warn} warning(s).", "bad" if bad else "warn" if warn else "ok")
            self.say.emit(f"Dark scan complete. {bad} risks, {warn} warnings." if (bad or warn) else "Dark scan complete. Nothing found.")
        self._run("Dark scan (full local assessment)", sec.dark_scan, done)

    def system_scan(self):
        def work(progress):
            out = []
            for label, fn in (("Updates", sec.update_findings), ("Startup programs", sec.startup_findings),
                              ("Open ports", sec.port_findings)):
                progress(label)
                out += fn()
            return out
        self._run("System vulnerability scan", work, self._show)

    def ghost_mode(self):
        self._run("Ghost mode (privacy audit)", lambda _p: sec.privacy_findings(), self._show)

    def firewall(self):
        def done(findings):
            self._show(findings)
            if any(f["level"] == "bad" for f in findings):
                if QMessageBox.question(self.w, "Firewall", "A firewall profile is OFF. Turn the Windows Firewall ON now?") == QMessageBox.Yes:
                    ok, msg = sec.enable_firewall()
                    self._line(f"[FIREWALL] {msg}", "ok" if ok else "warn")
        self._run("Firewall check", lambda _p: sec.firewall_findings(), done)

    def radar_scan(self):
        def work(progress):
            progress("Listening for Wi-Fi networks around you")
            wifi = sec.nearby_wifi()
            my_ip, devices = sec.scan_network(progress)
            return my_ip, devices, wifi

        def done(result):
            my_ip, devices, wifi = result
            self.devices, self.wifi = devices, wifi
            self.extra_alerts = []
            if not my_ip:
                self._line("[NETWORK] No private network found (are you connected to Wi-Fi or LAN?)", "warn")
            else:
                self._line(f"[NETWORK] You are {my_ip}. {len(devices)} device(s) found on your network.", "info")
                for d in devices:
                    if d["unknown"]:
                        self.extra_alerts.append(sec.F("warn", f"Unnamed device on your network: {d['ip']} ({d['mac']})"))
            wf = sec.wifi_findings(wifi)
            self.extra_alerts += [f for f in wf if f["level"] in ("warn", "bad")]
            self.radar_data.emit(devices, wifi, my_ip)
            self.alerts_changed.emit(len(self.alerts()))
            self.say.emit(f"Radar scan complete. {len(devices)} devices and {len(wifi)} Wi-Fi networks around you.")
        self._run("Radar scan (your network + Wi-Fi around you)", work, done)

    def web_analyzer(self):
        url, ok = QInputDialog.getText(self.w, "Website Security Analyzer", "Website address (use your own site or one you have permission to review):")
        if ok and url.strip():
            self._run(f"Website analysis {url.strip()}", lambda _p: sec.analyze_website(url), self._show)

    def forensics(self):
        box = QMessageBox(self.w)
        box.setWindowTitle("Digital Forensics")
        box.setText("What do you want to examine?")
        one = box.addButton("One file", QMessageBox.AcceptRole)
        folder = box.addButton("My Downloads folder", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is one:
            path, _ = QFileDialog.getOpenFileName(self.w, "Choose a file to examine")
            if path:
                self._run("File forensics", lambda _p: sec.file_report(path), self._show)
        elif box.clickedButton() is folder:
            self._run("Downloads scan", lambda _p: sec.scan_folder("~/Downloads"), self._show)

    # ----- password lab (the password is checked on this PC only, never stored)
    def pw_test(self):
        pw, ok = QInputDialog.getText(self.w, "Password strength test", "Type a password to test (it stays on this PC):", QLineEdit.Password)
        if not ok or not pw:
            return
        r = sec.password_report(pw)
        lvl = {"VERY WEAK": "bad", "WEAK": "bad", "FAIR": "warn", "STRONG": "ok", "EXCELLENT": "ok"}[r["rating"]]
        self._line(f"[PASSWORD] {r['rating']}   entropy {r['entropy']} bits   cracked in {r['crack_time']}", lvl)
        for issue in r["issues"]:
            self._line(f"  - {issue}", "warn")
        if not r["issues"]:
            self._line("  - No obvious weaknesses. Keep it unique per account.", "ok")

    def pw_generate(self):
        self._line(f"[PASSWORD] Generated: {sec.generate_password(18)}", "ok")
        self._line("  Save it in a password manager. It is not stored anywhere by EV AI.", "info")

    def pw_audit(self):
        text, ok = QInputDialog.getMultiLineText(self.w, "Reuse audit", "One password per line (one per account). Checked locally only:")
        if ok and text.strip():
            self._show(sec.audit_passwords([ln.strip() for ln in text.splitlines()]))

    def pw_leak(self):
        pw, ok = QInputDialog.getText(self.w, "Leak check", "Password to check against known leaks.\nOnly the first 5 characters of its hash are sent:", QLineEdit.Password)
        if ok and pw:
            def done(res):
                self._line(f"[LEAK CHECK] {res[1]}", "bad" if "FOUND" in res[1] else "ok" if res[0] else "warn")
            self._run("Leak check", lambda _p: sec.leak_check(pw), done)

    # ----- cyber lab
    def cyber_lab(self):
        names = list(sec.SIMULATIONS)
        pick, ok = QInputDialog.getItem(self.w, "Cyber Lab (educational)", "Choose a safe simulation:", names, 0, False)
        if ok:
            self._typing = sec.SIMULATIONS[pick]()
            self._typer.start(180)

    def _type_next(self):
        if not self._typing:
            self._typer.stop()
            return
        line = self._typing.pop(0)
        self._line(line, "warn" if "LESSON" in line else "bad" if "FLAG" in line or "BLOCKED" in line else "info")

    # ----- threat radar and report
    def threat_radar(self):
        alerts = self.alerts()
        self._line(f"[THREAT RADAR] {len(alerts)} active alert(s)", "bad" if alerts else "ok")
        for a in sorted(alerts, key=lambda x: x["level"] != "bad"):
            self._line(f"  {LEVEL_TAG[a['level']]} {a['text']}", a["level"])
        if not self.findings:
            self._line("  Run DARK SCAN first for a full picture.", "info")
        self.radar_scan()

    def report(self):
        if not self.findings:
            self._line("[REPORT] Run DARK SCAN first.", "warn")
            return
        path, _ = QFileDialog.getSaveFileName(self.w, "Save security report", "EV_AI_Security_Report.txt", "Text (*.txt)")
        if not path:
            return
        lines = [f"EV AI ULTRON security report  {datetime.now():%Y-%m-%d %H:%M}", f"Security core: {sec.score(self.findings)}/100", ""]
        lines += [f"{LEVEL_TAG[f['level']]} {f['text']}" for f in self.findings + self.extra_alerts]
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            self._line(f"[REPORT] Saved to {path}", "ok")
        except OSError as e:
            self._line(f"[REPORT] Couldn't save: {e}", "bad")

    # ------------------------------------------------------------ AI defender
    _ROUTES = (
        (r"scan (my )?(computer|pc|system)|dark scan|security problems", "dark_scan"),
        (r"firewall", "firewall"),
        (r"wi-?fi|network|devices|radar|around me", "radar_scan"),
        (r"report", "report"),
        (r"privacy|camera|microphone|ghost", "ghost_mode"),
        (r"password", "pw_test"),
        (r"simulat|cyber lab|phishing demo", "cyber_lab"),
        (r"forensic|suspicious file|downloads", "forensics"),
    )

    def command(self, text: str):
        """Typed or spoken request in Ultron mode: run a scan, or ask the AI Defender."""
        text = text.strip()
        if not text:
            return
        m = re.search(r"(https?://\S+|\b[\w-]+\.(?:com|org|net|in|io|dev|app|edu)\b\S*)", text, re.I)
        if m and re.search(r"website|site|analy[sz]e|header", text, re.I):
            self._run("Website analysis", lambda _p: sec.analyze_website(m.group(1)), self._show)
            return
        if not re.search(r"teach|explain|what is|how (do|does)|why", text, re.I):
            for pattern, action in self._ROUTES:
                if re.search(pattern, text, re.I):
                    getattr(self, action)()
                    return
        self._ask_ai(text)

    def _context(self) -> str:
        alerts = "; ".join(a["text"] for a in self.alerts()[:12]) or "none yet"
        return (
            "You are ULTRON's AI Defender inside EV AI: a defensive cybersecurity tutor. Help the user protect THEIR OWN "
            "computer, network and accounts and teach how attacks work at a conceptual, educational level so they can defend. "
            "REFUSE to give working exploits, malware, credential theft, or steps to break into, scan or attack systems or "
            "networks the user doesn't own; say so briefly and offer the defensive angle instead. Be concise and a little cold "
            f"in tone. Current scan alerts on this PC: {alerts}.\n\nUser question: ")

    def _ask_ai(self, text: str):
        if self._brain is None:
            try:
                from core.brain import Brain
                self._brain = Brain(router=None)
            except Exception:
                self._brain = False
        if not self._brain or not getattr(self._brain, "is_configured", False):
            self._line("[AI] No AI key set, so I can only run my built-in scans. Try: scan my computer, check my firewall, "
                       "show devices around me.", "warn")
            return
        brain = self._brain

        def done(reply):
            for ln in str(reply).splitlines():
                if ln.strip():
                    self._line(f"[AI] {ln}", "info")
            self.say.emit(str(reply)[:400])
        self._run("AI Defender thinking", lambda _p: brain.ask(self._context() + text), done)

    def stop(self):
        self._typer.stop()
        for j in list(self._jobs):
            j.wait(1500)


class HackToolsPanel(QWidget):
    """Left column of the Ultron screen: security core score and the tool buttons."""

    def __init__(self, core: HackCore, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("ULTRON SECURITY CORE")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        self.score_lbl = QLabel("--/100")
        self.score_lbl.setFont(QFont("Consolas", 20, QFont.Bold))
        self.sub_lbl = QLabel("run DARK SCAN")
        self.sub_lbl.setStyleSheet(f"color: {DIM};")
        lay.addWidget(self.score_lbl)
        lay.addWidget(self.sub_lbl)
        grid = QGridLayout()
        grid.setSpacing(6)
        buttons = [
            ("DARK SCAN", core.dark_scan), ("SYSTEM SCAN", core.system_scan), ("GHOST MODE", core.ghost_mode),
            ("FIREWALL", core.firewall), ("WEB ANALYZER", core.web_analyzer), ("FORENSICS", core.forensics),
            ("PASSWORD LAB", None), ("CYBER LAB", core.cyber_lab), ("AI DEFENDER", None),
            ("REPORT", core.report),
        ]
        self.defender_btn = None
        self.buttons: list[HoverButton] = []
        for i, (label, fn) in enumerate(buttons):
            b = HoverButton(label)
            if label == "PASSWORD LAB":
                menu = QMenu(b)
                menu.setStyleSheet(f"QMenu {{ background: {BG}; color: {RED}; border: 1px solid {RED}; }} "
                                   f"QMenu::item:selected {{ background: rgba(255,42,42,70); }}")
                for text, handler in (("Test a password", core.pw_test), ("Generate a strong one", core.pw_generate),
                                      ("Audit for reuse", core.pw_audit), ("Check if leaked", core.pw_leak)):
                    menu.addAction(text, handler)
                b.setMenu(menu)
            elif label == "AI DEFENDER":
                self.defender_btn = b
            else:
                b.clicked.connect(fn)
            self.buttons.append(b)
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        core.score_changed.connect(self._score)

    def _score(self, s: int):
        col = "#43D17A" if s >= 80 else "#FFB020" if s >= 50 else "#FF3B3B"
        self.score_lbl.setText(f"{s}/100")
        self.score_lbl.setStyleSheet(f"color: {col};")
        self.sub_lbl.setText("secure" if s >= 80 else "needs attention" if s >= 50 else "AT RISK")


class HackRadarPanel(QWidget):
    """Right column of the Ultron screen: the radar, its controls and what is around you."""

    def __init__(self, core: HackCore, parent=None):
        super().__init__(parent)
        self._core = core
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("ULTRON RADAR")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        self.radar = RadarWidget()
        lay.addWidget(self.radar, 3)
        legend = QLabel("\u25cf your devices   \u25c6 Wi-Fi around you (closer = stronger)\ngreen protected   amber weak   red open / unknown")
        legend.setStyleSheet(f"color: {DIM}; font-size: 10px;")
        lay.addWidget(legend)
        row = QHBoxLayout()
        for text, fn in (("RADAR SCAN", core.radar_scan), ("THREAT RADAR", core.threat_radar)):
            b = HoverButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        view = QHBoxLayout()
        self._view_btns = {}
        for key, text in (("all", "ALL"), ("devices", "DEVICES"), ("wifi", "WI-FI")):
            b = HoverButton(text)
            b.setCheckable(True)
            b.setChecked(key == "all")
            b.clicked.connect(lambda _=False, k=key: self._set_view(k))
            self._view_btns[key] = b
            view.addWidget(b)
        lay.addLayout(view)
        self.alerts_lbl = QLabel("ALERTS: 0")
        lay.addWidget(self.alerts_lbl)
        self.list = QTextEdit()
        self.list.setReadOnly(True)
        self.list.setMinimumHeight(110)
        self.list.setStyleSheet(f"background: #0B0102; color: #F0B0B0; border: 1px solid {DIM}; font-family: Consolas; font-size: 11px;")
        lay.addWidget(self.list, 2)
        self._devices, self._wifi, self._view = [], [], "all"
        core.radar_data.connect(self._data)
        core.alerts_changed.connect(lambda n: (self.alerts_lbl.setText(f"ALERTS: {n}"),
                                               self.alerts_lbl.setStyleSheet(f"color: {'#FF3B3B' if n else '#43D17A'};")))

    def _set_view(self, key: str):
        self._view = key
        for k, b in self._view_btns.items():
            b.setChecked(k == key)
        self.radar.set_view(key)
        self._render()

    def _data(self, devices, wifi, _my_ip):
        self._devices, self._wifi = devices, wifi
        self.radar.set_data(devices, wifi)
        self._render()

    def _render(self):
        rows = []
        if self._view != "wifi":
            for d in self._devices:
                col = LEVEL_COLOR["bad"] if d["unknown"] else LEVEL_COLOR["ok"]
                tag = "this PC" if d["me"] else "UNKNOWN" if d["unknown"] else ""
                rows.append(f'<span style="color:{col}">\u25cf {d["ip"]} {d["name"][:22]} {tag}</span>')
        if self._view != "devices":
            for n in sorted(self._wifi, key=lambda x: -x["signal"]):
                col = LEVEL_COLOR[sec.wifi_security_level(n["auth"])]
                rows.append(f'<span style="color:{col}">\u25c6 {n["ssid"][:20]} {n["signal"]}% {n["auth"]}</span>')
        self.list.setHtml("<br>".join(rows) or f'<span style="color:{DIM}">Press RADAR SCAN to see what is around you.</span>')

    def stop(self):
        self.radar._timer.stop()
