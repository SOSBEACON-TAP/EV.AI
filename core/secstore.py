"""
core/secstore.py
----------------
Small things Ultron remembers on THIS PC (data/ folder only):
  * the security score after each scan, so you can see if the PC is getting safer
  * the devices seen on your own Wi-Fi, so a NEW one can be flagged
  * which Windows settings page fixes which warning (the FIX button)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


def _dir() -> Path:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "data"


def _load(name: str, default):
    try:
        return json.loads((_dir() / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(name: str, obj) -> None:
    try:
        _dir().mkdir(parents=True, exist_ok=True)
        (_dir() / name).write_text(json.dumps(obj), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------- score history
def record_score(score: int, bad: int, warn: int, now: datetime | None = None) -> None:
    hist = _load("security_history.json", [])
    hist.append({"t": (now or datetime.now()).strftime("%Y-%m-%d %H:%M"), "score": int(score), "bad": int(bad), "warn": int(warn)})
    _save("security_history.json", hist[-60:])


def trend_text(hist: list | None = None) -> str:
    hist = _load("security_history.json", []) if hist is None else hist
    if not hist:
        return "No scans saved yet. Run DARK SCAN first."
    last = hist[-6:]
    line = ", ".join(str(h["score"]) for h in last)
    now = hist[-1]["score"]
    if len(hist) == 1:
        return f"Score {now}/100 (first scan saved)."
    diff = now - hist[-2]["score"]
    word = "up" if diff > 0 else "down" if diff < 0 else "the same"
    change = f"{word} {abs(diff)}" if diff else "the same"
    return f"Score {now}/100, {change} since the last scan. Recent scans: {line}. Best {max(h['score'] for h in hist)}, worst {min(h['score'] for h in hist)}."


# ---------------------------------------------------------------- new devices
def norm_mac(mac: str) -> str:
    m = (mac or "").strip().lower().replace("-", ":")
    return m if len(m.split(":")) == 6 else ""


def new_devices(devices: list[dict], now: datetime | None = None) -> tuple[list[dict], bool]:
    """Compares the devices on your Wi-Fi with the ones seen before. Returns (new devices, first_run).
    The first scan only saves a baseline, so it never raises false alarms."""
    known = _load("known_devices.json", {})
    first = not known
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    fresh = []
    for d in devices:
        mac = norm_mac(d.get("mac", ""))
        if not mac:
            continue
        if mac not in known:
            known[mac] = {"ip": d.get("ip", ""), "name": d.get("name", ""), "first_seen": stamp}
            if not first:
                fresh.append(d)
    _save("known_devices.json", known)
    return fresh, first


def forget_devices() -> None:
    _save("known_devices.json", {})


# ---------------------------------------------------------------- fix buttons
# (words in the warning, button text, what to open)
FIXES = [
    (("firewall",), "Open Firewall settings", "ms-settings:windowsdefender"),
    (("antivirus", "defender", "real-time", "definitions", "virus"), "Open Windows Security", "windowsdefender:"),
    (("update", "patch"), "Open Windows Update", "ms-settings:windowsupdate"),
    (("startup", "start with windows"), "Open Startup apps", "ms-settings:startupapps"),
    (("camera",), "Open Camera privacy", "ms-settings:privacy-webcam"),
    (("microphone", "mic "), "Open Microphone privacy", "ms-settings:privacy-microphone"),
    (("location",), "Open Location privacy", "ms-settings:privacy-location"),
    (("wi-fi", "wifi", "wep", "open network", "wpa"), "Open Wi-Fi settings", "ms-settings:network-wifi"),
    (("port", "listen"), "Open Firewall rules", "ms-settings:windowsdefender"),
]


def fixes_for(alert_texts: list[str]) -> list[tuple[str, str]]:
    """Unique (button text, target) pairs for the warnings you have right now."""
    out: list[tuple[str, str]] = []
    for text in alert_texts:
        low = text.lower()
        for words, label, target in FIXES:
            if any(w in low for w in words):
                if (label, target) not in out:
                    out.append((label, target))
                break
    return out
