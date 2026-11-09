"""Puts an "EV AI" icon on the Desktop and in the Start menu the first time the installed app runs,
like Discord or other apps do. If you delete the icon later it is not made again."""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path


def _flag(root: Path) -> Path:
    return root / "data" / "shortcuts_made.flag"


def _make(root: Path) -> None:
    exe = Path(sys.executable)
    ps = (
        "$s = New-Object -ComObject WScript.Shell;"
        f"$exe = '{exe}'; $dir = '{root}';"
        "foreach ($where in @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ''))) {"
        "  if (-not $where) { continue };"
        "  $l = $s.CreateShortcut((Join-Path $where 'EV AI.lnk'));"
        "  $l.TargetPath = $exe; $l.WorkingDirectory = $dir; $l.IconLocation = $exe + ',0';"
        "  $l.Description = 'EV AI'; $l.Save() }"
    )
    subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                   timeout=40, creationflags=0x08000000, capture_output=True)


def ensure_shortcuts(root: Path) -> None:
    """Runs in the background; does nothing outside the installed Windows app."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    flag = _flag(root)
    if flag.exists():
        return

    def work() -> None:
        try:
            _make(root)
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("ok", encoding="utf-8")
        except Exception as e:
            print(f"[EV AI] Shortcut creation skipped: {e}")
    threading.Thread(target=work, daemon=True).start()
