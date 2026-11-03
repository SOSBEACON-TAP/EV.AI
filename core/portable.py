"""
core/portable.py
----------------
Makes a portable copy of the EV AI app on a USB drive. On another Windows PC you open the
drive and double-click "Start EV AI.bat" (or EV_AI.exe inside the EV_AI folder). Windows blocks
programs from starting by themselves from USB drives, so it cannot open automatically.

Your keys (.env), face data, WhatsApp login and screenshots are left out unless you ask.
"""

import shutil
import sys
from pathlib import Path

# folders / files inside data\\ that are personal and only copied when asked
_SECRET_DATA = {"face_auth", "whatsapp_profile", "browser_profile", "screenshots"}
_NEVER = {"update_stage", "apply_update.bat", "update_busy.txt", "update_pending.json", "compute.json"}


def app_root() -> Path:
    return Path(sys.executable).resolve().parent


def estimate_bytes(src: Path, include_secrets: bool) -> int:
    total = 0
    for f in _walk(src, include_secrets):
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def _walk(src: Path, include_secrets: bool):
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        parts = rel.parts
        if parts[0] in ("_internal.old",) or (parts[0] == "data" and len(parts) > 1 and parts[1] in _NEVER):
            continue
        if parts[0] == "data" and len(parts) > 1 and parts[1] in _SECRET_DATA and not include_secrets:
            continue
        if parts[0] == ".env" and not include_secrets:
            continue
        yield p


def make_copy(src: Path, dest_drive: Path, include_secrets: bool, progress=None) -> Path:
    """Copies the app to <drive>\\EV_AI and writes 'Start EV AI.bat' next to it. Returns the folder."""
    if not (src / "EV_AI.exe").exists():
        raise RuntimeError("EV_AI.exe was not found next to the running app, so there is nothing to copy.")
    target = dest_drive / "EV_AI"
    target.mkdir(parents=True, exist_ok=True)
    files = list(_walk(src, include_secrets))
    total = max(1, sum(f.stat().st_size for f in files if f.exists()))
    done = 0
    for f in files:
        out = target / f.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
        done += f.stat().st_size
        if progress:
            progress(int(done * 100 / total))
    (dest_drive / "Start EV AI.bat").write_text(
        '@echo off\r\nstart "" "%~dp0EV_AI\\EV_AI.exe"\r\n', encoding="utf-8")
    (dest_drive / "EV AI - read me.txt").write_text(
        "EV AI on a USB drive\r\n\r\nOn any Windows PC: plug this drive in, open it and double-click "
        "'Start EV AI.bat'.\r\nWindows does not allow programs to start by themselves from USB drives.\r\n"
        "Your settings and memory are stored inside the EV_AI folder on this drive.\r\n"
        "If a SmartScreen warning appears, choose More info, then Run anyway.\r\n", encoding="utf-8")
    return target
