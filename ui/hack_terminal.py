"""
ui/hack_terminal.py
-------------------
ULTRON's HACK TERMINAL: a red-and-black defensive cybersecurity centre.
Everything checks YOUR OWN computer, network and files, or runs educational simulations on
made-up data. The radar shows what is around you: devices on your own network and the Wi-Fi
networks your adapter can hear, coloured by how well protected they are.
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from core import security as sec

RED, DIM, BG = "#FF2A2A", "#8A1A1A", "#070001"
LEVEL_COLOR = {"ok": "#43D17A", "info": "#E0B0B0", "warn": "#FFB020", "bad": "#FF3B3B"}
LEVEL_TAG = {"ok": "[ OK ]", "info": "[ .. ]", "warn": "[WARN]", "bad": "[RISK]"}

QSS = f"""
QDialog {{ background: {BG}; }}
QLabel {{ color: {RED}; font-family: Consolas, 'Courier New', monospace; }}
QPushButton {{ background: rgba(255,42,42,18); color: {RED}; border: 1px solid {DIM}; border-radius: 4px;
    padding: 8px 10px; font-family: Consolas, 'Courier New', monospace; font-weight: 700; letter-spacing: 1px; }}
QPushButton:hover {{ background: rgba(255,42,42,60); border: 1px solid {RED}; }}
QPushButton:disabled {{ color: #5a2a2a; border: 1px solid #3a1212; }}
QTextEdit, QLineEdit {{ background: #0B0102; color: #F0B0B0; border: 1px solid {DIM}; border-radius: 4px;
    font-family: Consolas, 'Courier New', monospace; font-size: 12px; selection-background-color: {RED}; }}
QLineEdit {{ padding: 7px; }}
"""


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
        self.setMinimumSize(320, 320)
        self._angle = 0.0
        self._devices: list[dict] = []
        self._wifi: list[dict] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_data(self, devices=None, wifi=None):
        if devices is not None:
            self._devices = devices
        if wifi is not None:
            self._wifi = wifi
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
        for n in self._wifi:
            ang, _d = self._spot(n["ssid"] + str(n.get("channel", "")), 0, 1)
            dist = r * (0.95 - 0.8 * min(100, n["signal"]) / 100)
            x, y = c.x() + dist * math.cos(ang), c.y() - dist * math.sin(ang)
            col = QColor(LEVEL_COLOR[sec.wifi_security_level(n["auth"])])
            self._glow(p, x, y, col, ang, diamond=True)
            p.setPen(QColor(col))
            p.setFont(QFont("Consolas", 7))
            p.drawText(QPointF(x + 7, y - 6), n["ssid"][:14])
        # devices on your own network: circles
        for d in self._devices:
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


class HackTerminal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ULTRON HACK TERMINAL")
        self.setStyleSheet(QSS)
        self.resize(1040, 680)
        self._jobs: list[_Job] = []
        self._findings: list[dict] = []          # latest dark-scan findings, drive score and alerts
        self._extra_alerts: list[dict] = []
        self._brain = None
        self._typing: list[str] = []

        root = QVBoxLayout(self)
        head = QHBoxLayout()
        title = QLabel("HACK TERMINAL")
        title.setFont(QFont("Consolas", 20, QFont.Bold))
        self.status = QLabel("SYSTEM READY")
        self.status.setFont(QFont("Consolas", 10))
        self.score_lbl = QLabel("SECURITY CORE  --/100")
        self.score_lbl.setFont(QFont("Consolas", 14, QFont.Bold))
        head.addWidget(title)
        head.addSpacing(18)
        head.addWidget(self.status)
        head.addStretch(1)
        head.addWidget(self.score_lbl)
        root.addLayout(head)
        note = QLabel("Defensive tools for YOUR OWN devices, network and files. Simulations use made-up data only.")
        note.setStyleSheet(f"color: {DIM};")
        root.addWidget(note)

        body = QHBoxLayout()
        left = QVBoxLayout()
        self.radar = RadarWidget()
        left.addWidget(self.radar, 1)
        legend = QLabel("● your devices   ◆ Wi-Fi around you (closer = stronger)\n"
                        "green = protected   amber = weak   red = open / unknown")
        legend.setStyleSheet(f"color: {DIM}; font-size: 10px;")
        left.addWidget(legend)
        body.addLayout(left, 4)

        right = QVBoxLayout()
        grid = QGridLayout()
        buttons = [
            ("DARK SCAN", self.dark_scan), ("RADAR SCAN", self.radar_scan), ("WEB ANALYZER", self.web_analyzer),
            ("SYSTEM SCAN", self.system_scan), ("GHOST MODE", self.ghost_mode), ("FIREWALL", self.firewall),
            ("FORENSICS", self.forensics), ("PASSWORD LAB", None), ("CYBER LAB", self.cyber_lab),
            ("THREAT RADAR", self.threat_radar), ("AI DEFENDER", self.ai_hint), ("REPORT", self.report),
        ]
        for i, (label, fn) in enumerate(buttons):
            b = QPushButton(label)
            if label == "PASSWORD LAB":
                menu = QMenu(b)
                menu.setStyleSheet(f"QMenu {{ background: {BG}; color: {RED}; border: 1px solid {RED}; }} "
                                   f"QMenu::item:selected {{ background: rgba(255,42,42,70); }}")
                for text, handler in (("Test a password", self.pw_test), ("Generate a strong one", self.pw_generate),
                                      ("Audit for reuse", self.pw_audit), ("Check if leaked", self.pw_leak)):
                    menu.addAction(text, handler)
                b.setMenu(menu)
            else:
                b.clicked.connect(fn)
            grid.addWidget(b, i // 3, i % 3)
        right.addLayout(grid)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        right.addWidget(self.log, 1)
        self.cmd = QLineEdit()
        self.cmd.setPlaceholderText('Ask the defender: "scan my computer", "check my firewall", "teach me about phishing"...')
        self.cmd.returnPressed.connect(self._command)
        right.addWidget(self.cmd)
        body.addLayout(right, 6)
        root.addLayout(body, 1)

        self._line("[SYSTEM] Security core initialized", "ok")
        self._line("[NETWORK] Monitoring ready", "ok")
        self._line("[AI] Defender online", "ok")
        QTimer(self, singleShot=True, interval=700, timeout=self.dark_scan).start()
        self._typer = QTimer(self)
        self._typer.timeout.connect(self._type_next)

    # ---------------------------------------------------------------- logging
    def _line(self, text: str, level: str = "info"):
        stamp = datetime.now().strftime("%H:%M:%S")
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;")
        self.log.append(f'<span style="color:{DIM}">{stamp}</span> <span style="color:{LEVEL_COLOR[level]}">{safe}</span>')

    def _show(self, findings: list[dict]):
        for f in findings:
            self._line(f"{LEVEL_TAG[f['level']]} {f['text']}", f["level"])

    def _set_score(self):
        s = sec.score(self._findings)
        col = "#43D17A" if s >= 80 else "#FFB020" if s >= 50 else "#FF3B3B"
        self.score_lbl.setText(f"SECURITY CORE  {s}/100")
        self.score_lbl.setStyleSheet(f"color: {col};")

    def _run(self, label: str, fn, on_done):
        self.status.setText(f"{label.upper()}...")
        self._line(f"[SCAN] {label} started", "info")
        job = _Job(fn, self)
        job.progress.connect(lambda t: self._line(f"[SCAN] {t}", "info"))
        job.failed.connect(lambda e: (self._line(f"[ERROR] {e}", "bad"), self.status.setText("SYSTEM READY")))
        job.finished_ok.connect(lambda r: (on_done(r), self.status.setText("SYSTEM READY")))
        job.finished.connect(lambda: self._jobs.remove(job) if job in self._jobs else None)
        self._jobs.append(job)
        job.start()

    # ---------------------------------------------------------------- actions
    def dark_scan(self):
        def done(findings):
            self._findings = findings
            self._show(findings)
            self._set_score()
            bad = sum(f["level"] == "bad" for f in findings)
            warn = sum(f["level"] == "warn" for f in findings)
            self._line(f"[DARK SCAN] Complete: {bad} risk(s), {warn} warning(s).", "bad" if bad else "warn" if warn else "ok")
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
                if QMessageBox.question(self, "Firewall", "A firewall profile is OFF. Turn the Windows Firewall ON now?") == QMessageBox.Yes:
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
            self.radar.set_data(devices, wifi)
            self._extra_alerts = []
            if not my_ip:
                self._line("[NETWORK] No private network found (are you connected to Wi-Fi or LAN?)", "warn")
            else:
                self._line(f"[NETWORK] You are {my_ip}. {len(devices)} device(s) found on your network:", "info")
                for d in devices:
                    tag = "(this PC)" if d["me"] else "UNKNOWN: no name, check you recognise it" if d["unknown"] else ""
                    lvl = "bad" if d["unknown"] else "ok"
                    self._line(f"  {d['ip']:<15} {d['mac']:<18} {d['name']:<28} {tag}", lvl)
                    if d["unknown"]:
                        self._extra_alerts.append(sec.F("warn", f"Unnamed device on your network: {d['ip']} ({d['mac']})"))
            wf = sec.wifi_findings(wifi)
            self._show(wf)
            self._extra_alerts += [f for f in wf if f["level"] in ("warn", "bad")]
        self._run("Radar scan (your network + Wi-Fi around you)", work, done)

    def web_analyzer(self):
        url, ok = QInputDialog.getText(self, "Website Security Analyzer", "Website address (use your own site or one you have permission to review):")
        if ok and url.strip():
            self._run(f"Website analysis {url.strip()}", lambda _p: sec.analyze_website(url), self._show)

    def forensics(self):
        box = QMessageBox(self)
        box.setWindowTitle("Digital Forensics")
        box.setText("What do you want to examine?")
        one = box.addButton("One file", QMessageBox.AcceptRole)
        folder = box.addButton("My Downloads folder", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is one:
            path, _ = QFileDialog.getOpenFileName(self, "Choose a file to examine")
            if path:
                self._run("File forensics", lambda _p: sec.file_report(path), self._show)
        elif box.clickedButton() is folder:
            self._run("Downloads scan", lambda _p: sec.scan_folder("~/Downloads"), self._show)

    # ----- password lab (the password is checked on this PC only, never stored)
    def pw_test(self):
        pw, ok = QInputDialog.getText(self, "Password strength test", "Type a password to test (it stays on this PC):", QLineEdit.Password)
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
        pw = sec.generate_password(18)
        self._line(f"[PASSWORD] Generated: {pw}", "ok")
        self._line("  Save it in a password manager. It is not stored anywhere by EV AI.", "info")

    def pw_audit(self):
        text, ok = QInputDialog.getMultiLineText(self, "Reuse audit", "One password per line (one per account). Checked locally only:")
        if ok and text.strip():
            self._show(sec.audit_passwords([ln.strip() for ln in text.splitlines()]))

    def pw_leak(self):
        pw, ok = QInputDialog.getText(self, "Leak check", "Password to check against known leaks.\nOnly the first 5 characters of its hash are sent:", QLineEdit.Password)
        if ok and pw:
            def done(res):
                self._line(f"[LEAK CHECK] {res[1]}", "bad" if "FOUND" in res[1] else "ok" if res[0] else "warn")
            self._run("Leak check", lambda _p: sec.leak_check(pw), done)

    # ----- cyber lab
    def cyber_lab(self):
        names = list(sec.SIMULATIONS)
        pick, ok = QInputDialog.getItem(self, "Cyber Lab (educational)", "Choose a safe simulation:", names, 0, False)
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
    def _alerts(self) -> list[dict]:
        return [f for f in self._findings + self._extra_alerts if f["level"] in ("warn", "bad")]

    def threat_radar(self):
        alerts = self._alerts()
        self._line(f"[THREAT RADAR] {len(alerts)} active alert(s)", "bad" if alerts else "ok")
        for a in sorted(alerts, key=lambda x: x["level"] != "bad"):
            self._line(f"  {LEVEL_TAG[a['level']]} {a['text']}", a["level"])
        if not self._findings:
            self._line("  Run DARK SCAN first for a full picture.", "info")
        self.radar_scan()

    def report(self):
        if not self._findings:
            self._line("[REPORT] Run DARK SCAN first.", "warn")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save security report", "EV_AI_Security_Report.txt", "Text (*.txt)")
        if not path:
            return
        lines = [f"EV AI ULTRON security report  {datetime.now():%Y-%m-%d %H:%M}", f"Security core: {sec.score(self._findings)}/100", ""]
        lines += [f"{LEVEL_TAG[f['level']]} {f['text']}" for f in self._findings + self._extra_alerts]
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            self._line(f"[REPORT] Saved to {path}", "ok")
        except OSError as e:
            self._line(f"[REPORT] Couldn't save: {e}", "bad")

    # ------------------------------------------------------------ AI defender
    def ai_hint(self):
        self.cmd.setFocus()
        self._line("[AI] Type a question below, for example: Teach me how phishing works.", "info")

    _ROUTES = (
        (r"scan (my )?(computer|pc|system)|dark scan|security problems", "dark_scan"),
        (r"firewall", "firewall"),
        (r"wi-?fi|network|devices|radar|around me", "radar_scan"),
        (r"report", "report"),
        (r"privacy|camera|microphone|ghost", "ghost_mode"),
        (r"password", "pw_test"),
    )

    def _command(self):
        text = self.cmd.text().strip()
        self.cmd.clear()
        if not text:
            return
        self._line(f"> {text}", "info")
        m = re.search(r"(https?://\S+|\b[\w-]+\.(?:com|org|net|in|io|dev|app|edu)\b\S*)", text, re.I)
        if m and re.search(r"website|site|analy[sz]e|header", text, re.I):
            self._run("Website analysis", lambda _p: sec.analyze_website(m.group(1)), self._show)
            return
        for pattern, action in self._ROUTES:
            if re.search(pattern, text, re.I) and not re.search(r"teach|explain|what is|how (do|does)", text, re.I):
                getattr(self, action)()
                return
        self._ask_ai(text)

    def _context(self) -> str:
        alerts = "; ".join(a["text"] for a in self._alerts()[:12]) or "none yet"
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
        self._run("AI Defender thinking", lambda _p: brain.ask(self._context() + text),
                  lambda reply: [self._line(f"[AI] {ln}", "info") for ln in str(reply).splitlines() if ln.strip()])

    def closeEvent(self, e):
        self.radar._timer.stop()
        self._typer.stop()
        for j in list(self._jobs):
            j.wait(1500)
        super().closeEvent(e)
