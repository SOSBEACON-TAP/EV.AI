"""
core/gamemode.py
----------------
Game mode helpers for YOUR OWN computer:
  * Clicker      : an auto-clicker (mouse button or a keyboard key) at a speed you choose
  * boost        : switch Windows to the High performance power plan, and back
  * top_apps     : the apps using the most memory, so you can close the ones you don't need while gaming

Honest limits: most online games with anti-cheat (Valorant, Fortnite, CS2 matchmaking, ...) treat auto-clickers as
cheating and can ban the account. Use it in single-player, idle/clicker games and tools. Some games ignore
synthetic clicks. Moving the mouse into the top-left corner of the screen always stops it.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time

IS_WIN = os.name == "nt"
_NOWIN = 0x08000000 if IS_WIN else 0
MAX_CPS = 50
HIGH_PERFORMANCE = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

_KEYS = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "esc": 0x1B,
         "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27}
_KEYS.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})
_KEYS.update({f"f{i}": 0x6F + i for i in range(1, 13)})


def vk_for(key: str) -> int | None:
    return _KEYS.get(key.strip().lower())


def key_names() -> list[str]:
    return list(_KEYS)


def _win_sender(kind: str, arg) -> None:
    import ctypes
    u = ctypes.windll.user32
    if kind == "mouse":
        down, up = (0x0002, 0x0004) if arg == "left" else (0x0008, 0x0010)
        u.mouse_event(down, 0, 0, 0, 0)
        u.mouse_event(up, 0, 0, 0, 0)
    else:
        u.keybd_event(arg, 0, 0, 0)
        u.keybd_event(arg, 0, 2, 0)


def _cursor_in_corner() -> bool:
    if not IS_WIN:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x <= 0 and pt.y <= 0
    except Exception:
        return False


class Clicker:
    """Auto-clicker. target is "left", "right" or a key name such as "e" or "space"."""

    def __init__(self, sender=None, corner_check=None):
        self._send = sender or (_win_sender if IS_WIN else (lambda kind, arg: None))
        self._corner = corner_check or _cursor_in_corner
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.count = 0
        self.stopped_reason = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, cps: float, target: str = "left", max_clicks: int = 0) -> bool:
        if self.running:
            return False
        target = target.strip().lower()
        if target in ("left", "right"):
            kind, arg = "mouse", target
        else:
            vk = vk_for(target)
            if vk is None:
                self.stopped_reason = f"Unknown key '{target}'."
                return False
            kind, arg = "key", vk
        cps = max(0.2, min(float(cps), MAX_CPS))
        self.count, self.stopped_reason = 0, ""
        self._stop.clear()

        def run():
            interval, nxt = 1.0 / cps, time.monotonic()
            while not self._stop.is_set():
                if self._corner():
                    self.stopped_reason = "Stopped: the mouse was moved to the top-left corner."
                    break
                self._send(kind, arg)
                self.count += 1
                if max_clicks and self.count >= max_clicks:
                    self.stopped_reason = "Finished."
                    break
                nxt += interval
                self._stop.wait(max(0.0, nxt - time.monotonic()))
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)


# ------------------------------------------------------------- performance
def _powercfg(*args: str) -> str:
    try:
        r = subprocess.run(["powercfg", *args], capture_output=True, text=True, timeout=15, creationflags=_NOWIN)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def parse_scheme_guid(text: str) -> str | None:
    m = re.search(r"([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})", text)
    return m.group(1).lower() if m else None


def current_scheme() -> str | None:
    return parse_scheme_guid(_powercfg("/getactivescheme"))


def boost() -> tuple[bool, str | None, str]:
    """Switches to High performance. Returns (ok, previous plan to restore later, message)."""
    if not IS_WIN:
        return False, None, "Power plans are a Windows feature."
    before = current_scheme()
    if before == HIGH_PERFORMANCE:
        return True, None, "Already on the High performance power plan."
    _powercfg("/setactive", HIGH_PERFORMANCE)
    now = current_scheme()
    if now == HIGH_PERFORMANCE:
        return True, before, "High performance power plan is on."
    return False, None, "Couldn't switch the power plan (this PC may hide the High performance plan)."


def restore(previous: str | None) -> str:
    if IS_WIN and previous:
        _powercfg("/setactive", previous)
        return "Power plan put back."
    return "Nothing to restore."


# ------------------------------------------------------------ background apps
_PROTECTED = {"system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
              "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe", "sihost.exe",
              "taskhostw.exe", "ctfmon.exe", "searchhost.exe", "startmenuexperiencehost.exe", "textinputhost.exe",
              "runtimebroker.exe", "shellexperiencehost.exe", "securityhealthservice.exe", "msmpeng.exe",
              "memory compression", "audiodg.exe", "conhost.exe", "wudfhost.exe", "spoolsv.exe", "dllhost.exe",
              "ev_ai.exe", "python.exe", "pythonw.exe", "steam.exe", "epicgameslauncher.exe", "discord.exe"}


def filter_apps(procs: list[tuple[int, str, int]], limit: int = 10, own_pid: int | None = None) -> list[dict]:
    """procs = [(pid, name, rss_bytes)] -> the biggest closable apps, grouped by name."""
    groups: dict[str, dict] = {}
    for pid, name, rss in procs:
        if not name or name.lower() in _PROTECTED or pid == own_pid:
            continue
        g = groups.setdefault(name, {"name": name, "pids": [], "mb": 0})
        g["pids"].append(pid)
        g["mb"] += int(rss / 1048576)
    return sorted(groups.values(), key=lambda g: -g["mb"])[:limit]


def top_apps(limit: int = 10) -> list[dict]:
    try:
        import psutil
        procs = [(p.info["pid"], p.info["name"], p.info["memory_info"].rss) for p in psutil.process_iter(["pid", "name", "memory_info"])
                 if p.info.get("memory_info")]
        return filter_apps(procs, limit, own_pid=os.getpid())
    except Exception:
        return []


def close_apps(names: list[str]) -> int:
    """Asks the chosen apps to close (terminate). Only names from top_apps are expected."""
    try:
        import psutil
    except ImportError:
        return 0
    n = 0
    for p in psutil.process_iter(["name"]):
        if p.info["name"] in names and (p.info["name"] or "").lower() not in _PROTECTED:
            try:
                p.terminate()
                n += 1
            except Exception:
                pass
    return n
