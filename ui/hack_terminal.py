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
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QStackedWidget, QTextEdit,
                               QVBoxLayout, QWidget, QGridLayout, QHBoxLayout)

from core import secstore, user_prefs
from core import antivirus, places, shell as shellmod
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


class LocationRadarWidget(QWidget):
    """North-up radar of real places around a point. Centre = you, rings = distance, colour = kind of place."""
    COLORS = {"hospital": "#FF5C5C", "clinic": "#FF5C5C", "pharmacy": "#FF5C5C", "police": "#5C9DFF", "fire station": "#5C9DFF",
              "atm": "#FFD24D", "bank": "#FFD24D", "restaurant": "#FF9A3C", "cafe": "#FF9A3C", "fast food": "#FF9A3C",
              "fuel": "#B388FF", "supermarket": "#69F0AE", "convenience": "#69F0AE"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self._places: list[dict] = []
        self._range = 1000
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, e):
        self._timer.start(40)
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def set_data(self, places_list, radius):
        self._places, self._range = places_list, radius
        self.update()

    def _tick(self):
        self._angle = (self._angle + 3.0) % 360
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        c = QPointF(w / 2, h / 2)
        r = min(w, h) / 2 - 12
        p.fillRect(self.rect(), QColor(BG))
        p.setPen(QPen(QColor(255, 42, 42, 70), 1))
        p.setFont(QFont("Consolas", 7))
        for i in (1, 2, 3, 4):
            p.drawEllipse(c, r * i / 4, r * i / 4)
            p.drawText(QPointF(c.x() + 3, c.y() - r * i / 4 + 10), places.nice(self._range * i / 4))
        p.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - r), QPointF(c.x(), c.y() + r))
        p.setPen(QColor(RED))
        p.setFont(QFont("Consolas", 9, QFont.Bold))
        p.drawText(QPointF(c.x() - 4, c.y() - r + 2), "N")
        for i in range(40):
            a = math.radians(self._angle - i * 1.6)
            p.setPen(QPen(QColor(255, 42, 42, max(0, 110 - i * 3)), 2))
            p.drawLine(c, QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a)))
        p.setFont(QFont("Consolas", 7))
        for pl in self._places:
            frac = min(1.0, pl["meters"] / self._range)
            ang = math.radians(90 - pl["bearing"])          # 0 deg = north = up
            x, y = c.x() + r * frac * math.cos(ang), c.y() - r * frac * math.sin(ang)
            col = QColor(self.COLORS.get(pl["kind"], "#4CC9F0"))
            flare = ((self._angle - math.degrees(ang)) % 360) < 40
            col.setAlpha(255 if flare else 150)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(x, y), 4, 4)
            p.setPen(col)
            p.drawText(QPointF(x + 7, y - 5), pl["name"][:14])
        p.setBrush(QColor(RED))
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, 5, 5)
        p.setPen(QPen(QColor(RED), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)


class HackCore(QObject):
    """The security engine. Output goes out through signals so any screen can show it."""
    line = Signal(str, str)            # text, level (ok/info/warn/bad)
    say = Signal(str)                  # something worth saying aloud (short)
    score_changed = Signal(int)
    radar_data = Signal(object, object, str)   # devices, wifi, my_ip
    alerts_changed = Signal(int)
    busy = Signal(str)                 # what is running now, "" when idle
    location_data = Signal(object, object, int)   # where you are (dict or None), places, radius

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
        self.shell = shellmod.Shell()

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
            secstore.record_score(sec.score(findings), bad, warn)
            self._line(f"[HISTORY] {secstore.trend_text()}", "info")
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
            fresh, first = secstore.new_devices(devices)
            if first and devices:
                self._line("[NETWORK] Saved these devices as your normal ones. From the next scan I will flag any new device.", "info")
            for d in fresh:
                msg = f"NEW device on your network: {d['ip']} ({d['mac']}, {d.get('name', '?')}). If it is not yours, change your Wi-Fi password."
                self._line(f"[ALERT] {msg}", "bad")
                self.extra_alerts.append(sec.F("bad", msg))
            if fresh:
                self.say.emit(f"Alert. {len(fresh)} new device joined your network.")
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

    # ----- antivirus (Microsoft Defender)
    def _av_done(self, label):
        def done(res):
            ok, msg = res
            self._line(f"[ANTIVIRUS] {label}: {msg}", "ok" if ok else "warn")
            if ok and "finished" in msg:
                self.av_threats()
        return done

    def av_quick(self):
        self._run("Antivirus quick scan", lambda _p: antivirus.scan("quick"), self._av_done("Quick scan"))

    def av_full(self):
        if QMessageBox.question(self.w, "Full scan", "A full scan can take an hour or more and slows the PC. Start it?") == QMessageBox.Yes:
            self._run("Antivirus full scan", lambda _p: antivirus.scan("full"), self._av_done("Full scan"))

    def av_file(self):
        box = QMessageBox(self.w)
        box.setWindowTitle("Scan for viruses")
        box.setText("What do you want to scan?")
        one = box.addButton("One file", QMessageBox.AcceptRole)
        folder = box.addButton("A folder", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        path = ""
        if box.clickedButton() is one:
            path, _ = QFileDialog.getOpenFileName(self.w, "Choose a file to scan")
        elif box.clickedButton() is folder:
            path = QFileDialog.getExistingDirectory(self.w, "Choose a folder to scan")
        if path:
            self._run("Antivirus custom scan", lambda _p: antivirus.scan("custom", path), self._av_done("Custom scan"))

    def av_update(self):
        self._run("Updating virus definitions", lambda _p: antivirus.update_definitions(),
                  lambda r: self._line(f"[ANTIVIRUS] {r[1]}", "ok" if r[0] else "warn"))

    def av_threats(self):
        def done(found):
            if not found:
                self._line("[ANTIVIRUS] No threats on record.", "ok")
            for t in found:
                lvl = "bad" if t["status"] == "ACTIVE" else "warn"
                self._line(f"[THREAT] {t['name']}  severity {t['severity']}  {t['status']}  {t['resources']}", lvl)
            if any(t["status"] == "ACTIVE" for t in found):
                self.say.emit("Active threat found. Open Windows Security to remove it.")
        self._run("Reading threat list", lambda _p: antivirus.threats(), done)

    # ----- location radar
    def set_my_location(self, text: str):
        """'set location Anna Nagar, Chennai': remember a place you typed, used instead of the internet guess."""
        def work(progress):
            progress("Looking that place up (OpenStreetMap)")
            return places.geocode(text)

        def done(loc):
            if not loc:
                self._line("[LOCATION] Couldn't find that place. Try a fuller name, e.g. set location T Nagar, Chennai.", "warn")
                return
            user_prefs.set_value("home_lat", loc["lat"])
            user_prefs.set_value("home_lon", loc["lon"])
            user_prefs.set_value("home_name", loc["city"])
            self._line(f"[LOCATION] Saved: {loc['city']}. The Location radar will use this. Say 'forget location' to remove it.", "ok")
            self.location_scan()
        self._run("Set location", work, done)

    def history(self):
        self._line(f"[HISTORY] {secstore.trend_text()}", "info")

    def forget_devices(self):
        secstore.forget_devices()
        self._line("[NETWORK] Known devices cleared. The next radar scan saves a fresh list.", "ok")

    def open_fix(self, target: str):
        """Opens the Windows settings page that fixes a warning (only fixed ms-settings / windowsdefender pages)."""
        import os
        if os.name == "nt" and target.startswith(("ms-settings:", "windowsdefender:")):
            try:
                os.startfile(target)
                return
            except OSError:
                pass
        self._line(f"[FIX] Open Windows Settings and search for it ({target}).", "warn")

    def forget_location(self):
        for k in ("home_lat", "home_lon", "home_name"):
            user_prefs.set_value(k, user_prefs.DEFAULTS[k])
        self._line("[LOCATION] Saved location removed.", "ok")

    def location_scan(self, radius: int = 1000):
        def work(progress):
            loc = None
            lat, lon = user_prefs.get("home_lat"), user_prefs.get("home_lon")
            if lat and lon:
                progress("Using the location you saved")
                loc = {"lat": float(lat), "lon": float(lon), "city": user_prefs.get("home_name") or "your saved place",
                       "region": "", "country": "", "source": "saved"}
            if not loc:
                progress("Asking Windows for your position (Wi-Fi / GPS)")
                loc = places.windows_location()
            if not loc:
                progress("Finding your approximate position (from your internet connection)")
                loc = places.approximate_location()
            if not loc:
                return None, [], radius
            progress(f"Looking for places within {places.nice(radius)} (OpenStreetMap)")
            try:
                return loc, places.nearby_places(loc["lat"], loc["lon"], radius), radius
            except Exception:
                return loc, [], radius

        def done(res):
            loc, found, rad = res
            if not loc:
                self._line("[LOCATION] Couldn't work out your position (no internet?).", "warn")
            else:
                src = loc.get("source")
                if src == "windows":
                    self._line(f"[LOCATION] Windows position, accurate to about {int(loc.get('accuracy', 0))} m", "ok")
                elif src in ("saved", "typed"):
                    self._line(f"[LOCATION] {loc['city']} (the place you set)", "info")
                else:
                    self._line(f"[LOCATION] Approximately {loc['city']}, {loc['region']}, {loc['country']} (from your internet connection, only city level and often off. "
                               "Turn on Windows location, or type: set location <your area, city>)", "warn")
                self._line(f"[LOCATION] {len(found)} place(s) within {places.nice(rad)}", "ok" if found else "info")
            self.location_data.emit(loc, found, rad)
        self._run("Location radar", work, done)

    # ----- terminal
    def run_shell(self, cmd: str):
        if not cmd:
            self._line(f"[CMD] folder: {self.shell.cwd}   (type > then a command, for example > ipconfig)", "info")
            return
        if shellmod.is_dangerous(cmd):
            if QMessageBox.warning(self.w, "Run this command?", f"This command can delete data or change the system:\n\n{cmd}\n\nRun it?",
                                   QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
                self._line("[CMD] Cancelled.", "warn")
                return
        self._line(f"{self.shell.cwd}> {cmd}", "info")

        def done(out):
            for ln in str(out).splitlines():
                self._line("  " + ln, "info")
        self._run(f"Command: {cmd[:40]}", lambda _p: self.shell.run(cmd), done)

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
        shell_cmd = shellmod.strip_prefix(text)
        if shell_cmd is not None:                     # "> dir" or "cmd dir": run it in the terminal
            self.run_shell(shell_cmd)
            return
        low = text.lower()
        ml = re.match(r"\s*(?:set|change)\s+(?:my\s+)?location\s+(?:to\s+)?(.+)", text, re.I)
        if ml:
            self.set_my_location(ml.group(1).strip())
            return
        for phrase, fn in (("quick scan", self.av_quick), ("full scan", self.av_full), ("virus", self.av_quick),
                           ("antivirus", self.av_quick), ("threat", self.av_threats),
                           ("forget location", self.forget_location), ("forget devices", self.forget_devices), ("score history", self.history), ("security history", self.history), ("where am i", self.location_scan), ("location", self.location_scan)):
            if phrase in low and not re.search(r"teach|explain|what is|how (do|does)|why", low):
                fn()
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

    # ----- used by the Ultron terminal window (it shows the result itself, not in the conversation)
    def _get_brain(self):
        if self._brain is None:
            try:
                from core.brain import Brain
                self._brain = Brain(router=None)
            except Exception:
                self._brain = False
        return self._brain if (self._brain and getattr(self._brain, "is_configured", False)) else None

    def _quiet_job(self, fn, on_done, on_fail):
        job = _Job(fn, self)
        job.failed.connect(lambda e: on_fail(e))
        job.finished_ok.connect(lambda r: on_done(r))
        job.finished.connect(lambda: self._jobs.remove(job) if job in self._jobs else None)
        self._jobs.append(job)
        job.start()

    def explain_code(self, code: str, on_done, on_fail):
        """Ultron explains the code that was typed or pasted. on_done(text) / on_fail(text)."""
        brain = self._get_brain()
        if brain is None:
            on_fail("No AI key is set, so I can't explain code. Add a key in Settings. I can still run commands: start a line with >")
            return
        prompt = ("You are ULTRON inside EV AI, explaining code to its owner. Explain the code below in plain text, no markdown: "
                  "first one line saying what it does overall, then go through it step by step, then list any bugs or security "
                  "risks you notice. Be concise and a little cold in tone. Only explain; do not write new malware or exploits.\n\nCODE:\n"
                  + code[:6000])
        self._quiet_job(lambda _p: brain.ask(prompt), lambda r: on_done(str(r)), on_fail)

    def run_command(self, cmd: str, on_done, on_fail) -> bool:
        """Runs one Windows command and hands the output to on_done. Asks first if it can delete data or change the system."""
        if shellmod.is_dangerous(cmd):
            if QMessageBox.warning(self.w, "Run this command?", f"This command can delete data or change the system:\n\n{cmd}\n\nRun it?",
                                   QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
                return False
        self._quiet_job(lambda _p: self.shell.run(cmd), lambda r: on_done(str(r)), on_fail)
        return True

    def stop(self):
        self._typer.stop()
        for j in list(self._jobs):
            j.wait(1500)


class HackToolsPanel(QWidget):
    """Left column of the Ultron screen: security core score, security tools, antivirus and terminal."""

    def __init__(self, core: HackCore, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("ULTRON SECURITY CORE")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        self.score_lbl = QLabel("--/100")
        self.score_lbl.setFont(QFont("Consolas", 16, QFont.Bold))
        self.sub_lbl = QLabel("run DARK SCAN")
        self.sub_lbl.setStyleSheet(f"color: {DIM};")
        lay.addWidget(self.score_lbl)
        lay.addWidget(self.sub_lbl)
        self.buttons: list[HoverButton] = []
        self.defender_btn = None
        self.terminal_btn = None

        compact = "QPushButton { padding: 4px 2px; font-size: 9px; letter-spacing: 1px; }"

        def group(name, items, columns=3):
            lab = QLabel(name)
            lab.setObjectName("SectionTitle")
            lab.setStyleSheet("margin-top: 2px;")
            lay.addWidget(lab)
            grid = QGridLayout()
            grid.setSpacing(4)
            for i, (label, fn) in enumerate(items):
                b = HoverButton(label)
                b.setStyleSheet(compact)
                b.setMinimumHeight(26)
                if label == "PASSWORDS":
                    menu = QMenu(b)
                    menu.setStyleSheet(f"QMenu {{ background: {BG}; color: {RED}; border: 1px solid {RED}; }} "
                                       f"QMenu::item:selected {{ background: rgba(255,42,42,70); }}")
                    for text, handler in (("Test a password", core.pw_test), ("Generate a strong one", core.pw_generate),
                                          ("Audit for reuse", core.pw_audit), ("Check if leaked", core.pw_leak)):
                        menu.addAction(text, handler)
                    b.setMenu(menu)
                elif label == "FIX WARNINGS":
                    fix_menu = QMenu(b)
                    fix_menu.setStyleSheet(f"QMenu {{ background: {BG}; color: {RED}; border: 1px solid {RED}; }} "
                                           f"QMenu::item:selected {{ background: rgba(255,42,42,70); }}")

                    def fill(menu=fix_menu):
                        menu.clear()
                        fixes = secstore.fixes_for([a["text"] for a in core.alerts()])
                        if not fixes:
                            menu.addAction("No warnings to fix (run DARK SCAN first)").setEnabled(False)
                        for text, target in fixes:
                            menu.addAction(text, lambda t=target: core.open_fix(t))
                    fix_menu.aboutToShow.connect(fill)
                    b.setMenu(fix_menu)
                elif fn is not None:
                    b.clicked.connect(fn)
                if label == "AI DEFENDER":
                    self.defender_btn = b
                if label == "OPEN TERMINAL":
                    self.terminal_btn = b
                self.buttons.append(b)
                grid.addWidget(b, i // columns, i % columns)
            lay.addLayout(grid)

        group("SECURITY", [
            ("DARK SCAN", core.dark_scan), ("SYSTEM SCAN", core.system_scan), ("GHOST MODE", core.ghost_mode),
            ("FIREWALL", core.firewall), ("WEB ANALYZER", core.web_analyzer), ("FORENSICS", core.forensics),
            ("PASSWORDS", None), ("CYBER LAB", core.cyber_lab), ("AI DEFENDER", None), ("REPORT", core.report),
            ("HISTORY", core.history), ("FIX WARNINGS", None)])
        group("ANTIVIRUS", [
            ("QUICK SCAN", core.av_quick), ("FULL SCAN", core.av_full), ("SCAN FILE", core.av_file),
            ("UPDATE DEFS", core.av_update), ("THREATS", core.av_threats)])
        group("TERMINAL", [("OPEN TERMINAL", None)], columns=1)
        lay.addStretch(1)
        core.score_changed.connect(self._score)

    def _score(self, s: int):
        col = "#43D17A" if s >= 80 else "#FFB020" if s >= 50 else "#FF3B3B"
        self.score_lbl.setText(f"{s}/100")
        self.score_lbl.setStyleSheet(f"color: {col};")
        self.sub_lbl.setText("secure" if s >= 80 else "needs attention" if s >= 50 else "AT RISK")


class HackRadarPanel(QWidget):
    """Right column of the Ultron screen: two radars (Wi-Fi and location) with their controls and lists."""

    def __init__(self, core: HackCore, parent=None):
        super().__init__(parent)
        self._core = core
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("ULTRON RADAR")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        tabs = QHBoxLayout()
        self._tab_btns = {}
        for key, text in ((0, "WI-FI RADAR"), (1, "LOCATION RADAR")):
            b = HoverButton(text)
            b.setCheckable(True)
            b.setChecked(key == 0)
            b.clicked.connect(lambda _=False, k=key: self._tab(k))
            self._tab_btns[key] = b
            tabs.addWidget(b)
        lay.addLayout(tabs)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        # --- page 0: Wi-Fi radar ---
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        self.radar = RadarWidget()
        pl.addWidget(self.radar, 3)
        legend = QLabel("\u25cf your devices   \u25c6 Wi-Fi around you (closer = stronger)\ngreen protected   amber weak   red open / unknown")
        legend.setStyleSheet(f"color: {DIM}; font-size: 10px;")
        pl.addWidget(legend)
        row = QHBoxLayout()
        for text, fn in (("RADAR SCAN", core.radar_scan), ("THREAT RADAR", core.threat_radar)):
            b = HoverButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        pl.addLayout(row)
        view = QHBoxLayout()
        self._view_btns = {}
        for key, text in (("all", "ALL"), ("devices", "DEVICES"), ("wifi", "WI-FI")):
            b = HoverButton(text)
            b.setCheckable(True)
            b.setChecked(key == "all")
            b.clicked.connect(lambda _=False, k=key: self._set_view(k))
            self._view_btns[key] = b
            view.addWidget(b)
        pl.addLayout(view)
        self.alerts_lbl = QLabel("ALERTS: 0")
        pl.addWidget(self.alerts_lbl)
        self.list = self._list_box()
        pl.addWidget(self.list, 2)
        self.stack.addWidget(page)

        # --- page 1: location radar ---
        page2 = QWidget()
        ql = QVBoxLayout(page2)
        ql.setContentsMargins(0, 0, 0, 0)
        self.loc_radar = LocationRadarWidget()
        ql.addWidget(self.loc_radar, 3)
        self.loc_lbl = QLabel("Press LOCATE ME. A PC has no GPS: the position comes from your internet connection (city level).")
        self.loc_lbl.setWordWrap(True)
        self.loc_lbl.setStyleSheet(f"color: {DIM}; font-size: 10px;")
        ql.addWidget(self.loc_lbl)
        rrow = QHBoxLayout()
        self._range = 1000
        b = HoverButton("LOCATE ME")
        b.clicked.connect(lambda: core.location_scan(self._range))
        rrow.addWidget(b)
        self._range_btns = {}
        for m in (500, 1000, 2000):
            rb = HoverButton(places.nice(m).replace(" ", ""))
            rb.setCheckable(True)
            rb.setChecked(m == 1000)
            rb.clicked.connect(lambda _=False, v=m: self._set_range(v))
            self._range_btns[m] = rb
            rrow.addWidget(rb)
        ql.addLayout(rrow)
        self.loc_list = self._list_box()
        ql.addWidget(self.loc_list, 2)
        self.stack.addWidget(page2)

        self._devices, self._wifi, self._view = [], [], "all"
        core.radar_data.connect(self._data)
        core.location_data.connect(self._location)
        core.alerts_changed.connect(lambda n: (self.alerts_lbl.setText(f"ALERTS: {n}"),
                                               self.alerts_lbl.setStyleSheet(f"color: {'#FF3B3B' if n else '#43D17A'};")))

    def _list_box(self) -> QTextEdit:
        box = QTextEdit()
        box.setReadOnly(True)
        box.setMinimumHeight(110)
        box.setStyleSheet(f"background: #0B0102; color: #F0B0B0; border: 1px solid {DIM}; font-family: Consolas; font-size: 11px;")
        return box

    def _tab(self, k: int):
        self.stack.setCurrentIndex(k)
        for key, b in self._tab_btns.items():
            b.setChecked(key == k)

    def _set_range(self, v: int):
        self._range = v
        for m, b in self._range_btns.items():
            b.setChecked(m == v)

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

    def _location(self, loc, found, radius):
        self.loc_radar.set_data(found, radius)
        if loc:
            self.loc_lbl.setText(f"Approximately {loc['city']}, {loc['region']}, {loc['country']}. {len(found)} place(s) within {places.nice(radius)}.")
        rows = [f'<span style="color:{LocationRadarWidget.COLORS.get(p["kind"], "#4CC9F0")}">\u25cf {p["name"][:24]} - {p["kind"]} - {places.nice(p["meters"])} {places.compass(p["bearing"])}</span>'
                for p in found[:40]]
        self.loc_list.setHtml("<br>".join(rows) or f'<span style="color:{DIM}">No mapped places found.</span>')

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
        self.loc_radar._timer.stop()
