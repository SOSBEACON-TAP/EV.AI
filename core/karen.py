"""
core/karen.py
-------------
KAREN MODE: visible parental controls for THIS Windows PC.
  * a PIN protects the rules (stored as a salted hash, never the PIN itself)
  * daily screen-time limit and a bedtime window: the PC locks when time is up
  * blocked apps are closed, blocked websites are blocked in Chrome (through the EV AI extension)
  * a usage report (time per app) so the child can see it too

It is NOT hidden spying: the screen says Karen mode is on, and the rules and the report can be read by anyone.
Honest limit: EV AI is a normal program, so a determined user can close it from Task Manager. For tamper-proof
controls use Windows Family Safety (family.microsoft.com) alongside it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

IS_WIN = os.name == "nt"
_NOWIN = 0x08000000 if IS_WIN else 0
IDLE_LIMIT_S = 60              # no keyboard/mouse for a minute = not counted as screen time
MAX_WRONG, LOCKOUT_S = 5, 300


def _default_path() -> Path:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "data" / "karen.json"


def _hash(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000).hex()


def parse_hhmm(text: str) -> int:
    h, m = text.strip().split(":")
    return int(h) * 60 + int(m)


def clean_sites(lines) -> list[str]:
    """'https://www.YouTube.com/watch' -> 'youtube.com'. Only plain domains are kept."""
    out = []
    for raw in lines:
        s = raw.strip().lower().replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        s = s[4:] if s.startswith("www.") else s
        if s and all(c.isalnum() or c in ".-" for c in s) and "." in s and s not in out:
            out.append(s)
    return out


class Karen:
    def __init__(self, path: Path | None = None):
        self.path = path or _default_path()
        self.data = {"enabled": False, "pin_hash": "", "salt": "", "daily_limit_min": 120, "bed_on": True,
                     "bed_start": "21:00", "bed_end": "07:00", "blocked_apps": [], "blocked_sites": [],
                     "usage": {}, "extra": {}}
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            pass
        self._wrong, self._locked_until = 0, 0.0
        self._warned: set[str] = set()
        self._last_lock = 0.0

    # ---------------------------------------------------------- storage
    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
        except OSError:
            pass

    @property
    def enabled(self) -> bool:
        return bool(self.data["enabled"])

    @property
    def has_pin(self) -> bool:
        return bool(self.data["pin_hash"])

    # -------------------------------------------------------------- PIN
    def set_pin(self, pin: str) -> bool:
        if len(pin) < 4:
            return False
        salt = secrets.token_bytes(16)
        self.data["salt"], self.data["pin_hash"] = salt.hex(), _hash(pin, salt)
        self.save()
        return True

    def check_pin(self, pin: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if now < self._locked_until or not self.has_pin:
            return False
        ok = hmac.compare_digest(_hash(pin, bytes.fromhex(self.data["salt"])), self.data["pin_hash"])
        if ok:
            self._wrong = 0
            return True
        self._wrong += 1
        if self._wrong >= MAX_WRONG:
            self._locked_until, self._wrong = now + LOCKOUT_S, 0
        return False

    def pin_locked_for(self, now: float | None = None) -> int:
        return max(0, int(self._locked_until - (time.time() if now is None else now)))

    # ------------------------------------------------------------ rules
    def set_enabled(self, on: bool) -> None:
        self.data["enabled"] = bool(on)
        self._warned.clear()
        self.save()

    def set_rules(self, daily_limit_min: int, bed_on: bool, bed_start: str, bed_end: str, apps, sites) -> None:
        parse_hhmm(bed_start), parse_hhmm(bed_end)          # raises on bad input
        self.data.update(daily_limit_min=max(0, int(daily_limit_min)), bed_on=bool(bed_on), bed_start=bed_start,
                         bed_end=bed_end,
                         blocked_apps=[a.strip().lower() for a in apps if a.strip()],
                         blocked_sites=clean_sites(sites))
        self.save()

    def grant_minutes(self, n: int, today: str | None = None) -> None:
        day = today or date.today().isoformat()
        self.data["extra"] = {day: self.data["extra"].get(day, 0) + max(0, int(n))}
        self.save()

    # ----------------------------------------------------------- checks
    def in_bedtime(self, now: datetime) -> bool:
        if not self.data["bed_on"]:
            return False
        a, b, t = parse_hhmm(self.data["bed_start"]), parse_hhmm(self.data["bed_end"]), now.hour * 60 + now.minute
        return (a <= t < b) if a <= b else (t >= a or t < b)

    def used_today(self, today: str | None = None) -> int:
        return int(self.data["usage"].get(today or date.today().isoformat(), {}).get("total", 0))

    def limit_seconds(self, today: str | None = None) -> int:
        day = today or date.today().isoformat()
        return (int(self.data["daily_limit_min"]) + int(self.data["extra"].get(day, 0))) * 60

    def remaining_seconds(self, today: str | None = None) -> int:
        if not self.data["daily_limit_min"]:
            return 10 ** 9                                  # 0 = no daily limit
        return self.limit_seconds(today) - self.used_today(today)

    def tick(self, now: datetime, foreground: str, idle_s: float, dt: float, running: set[str] | None = None) -> list[dict]:
        """Call every few seconds. Returns what to do: {"do": "lock"|"kill"|"warn", "text": ..., "name": ...}."""
        if not self.enabled:
            return []
        day = now.date().isoformat()
        acts: list[dict] = []
        if idle_s < IDLE_LIMIT_S:
            u = self.data["usage"].setdefault(day, {"total": 0, "apps": {}})
            u["total"] += dt
            if foreground:
                u["apps"][foreground] = u["apps"].get(foreground, 0) + dt
            for old in sorted(self.data["usage"])[:-30]:
                self.data["usage"].pop(old, None)
        stamp = time.monotonic()
        if self.in_bedtime(now):
            if stamp - self._last_lock > 45:
                self._last_lock = stamp
                acts.append({"do": "lock", "text": "It is bedtime. Karen mode is locking the computer."})
        elif self.data["daily_limit_min"]:
            left = self.remaining_seconds(day)
            if left <= 0:
                if stamp - self._last_lock > 45:
                    self._last_lock = stamp
                    acts.append({"do": "lock", "text": "Today's screen time is used up. Karen mode is locking the computer."})
            elif left <= 60 and "1" not in self._warned:
                self._warned.add("1")
                acts.append({"do": "warn", "text": "One minute of screen time left today."})
            elif left <= 300 and "5" not in self._warned:
                self._warned.add("5")
                acts.append({"do": "warn", "text": "Five minutes of screen time left today."})
        blocked = set(self.data["blocked_apps"])
        for name in (running or set()):
            if name.lower() in blocked:
                acts.append({"do": "kill", "name": name, "text": f"{name} is blocked by Karen mode."})
        return acts

    # ----------------------------------------------------------- report
    def report(self, days: int = 7, today: date | None = None) -> str:
        today = today or date.today()
        lines = [f"KAREN MODE report (last {days} days)", ""]
        for i in range(days):
            d = (today - timedelta(days=i)).isoformat()
            u = self.data["usage"].get(d)
            if not u:
                continue
            lines.append(f"{d}   total {int(u['total'] // 60)} min")
            for app, sec in sorted(u["apps"].items(), key=lambda kv: -kv[1])[:5]:
                lines.append(f"      {app:<28} {int(sec // 60)} min")
        if len(lines) == 2:
            lines.append("No usage recorded yet.")
        return "\n".join(lines)

    def status_line(self, now: datetime | None = None) -> str:
        now = now or datetime.now()
        if not self.enabled:
            return "Karen mode is OFF."
        limit = self.data["daily_limit_min"]
        used = self.used_today(now.date().isoformat()) // 60
        parts = [f"Karen mode is ON. Used today: {used} min" + (f" of {limit + self.data['extra'].get(now.date().isoformat(), 0)} min" if limit else "")]
        if self.data["bed_on"]:
            parts.append(f"bedtime {self.data['bed_start']} to {self.data['bed_end']}")
        return ", ".join(parts) + "."


# --------------------------------------------------------- Windows helpers
def foreground_process() -> str:
    if not IS_WIN:
        return ""
    try:
        import ctypes
        import psutil
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def idle_seconds() -> float:
    if not IS_WIN:
        return 0.0
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0
    except Exception:
        return 0.0


def running_names(wanted: set[str]) -> set[str]:
    if not wanted:
        return set()
    try:
        import psutil
        return {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])} & wanted
    except Exception:
        return set()


def kill_by_name(name: str) -> int:
    try:
        import psutil
        n = 0
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() == name.lower():
                try:
                    p.terminate()
                    n += 1
                except Exception:
                    pass
        return n
    except Exception:
        return 0


def lock_workstation() -> None:
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        except Exception:
            pass
