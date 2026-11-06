"""
core/shell.py
-------------
Run Windows commands from Ultron's terminal, on YOUR OWN computer, as you.
  * Commands starting with ">" (or "cmd ") in Ultron's chat box come here.
  * `cd` is handled here so the folder is remembered between commands.
  * Risky commands (delete, format, shutdown, registry changes...) are flagged so the screen asks first.
  * Each command stops after 60 seconds, and output is cut at 20,000 characters.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_NOWIN = 0x08000000 if os.name == "nt" else 0
TIMEOUT = 60
MAX_OUT = 20000

_DANGEROUS = re.compile(
    r"(^|[\s&|;(])(del|erase|rd|rmdir|format|diskpart|shutdown|restart-computer|stop-computer|"
    r"reg\s+(delete|add|import)|takeown|icacls|cipher\s+/w|bcdedit|sfc|dism|net\s+user|net\s+localgroup|"
    r"taskkill|wmic|rm|mkfs|dd|remove-item|set-executionpolicy|netsh\s+advfirewall)\b", re.I)


def is_dangerous(cmd: str) -> bool:
    """True if the command can delete data, change the system, or stop programs. The UI asks before running it."""
    return bool(_DANGEROUS.search(cmd))


def strip_prefix(text: str) -> str | None:
    """'> dir' or 'cmd dir' -> 'dir'; anything else -> None (it is not a terminal command)."""
    t = text.strip()
    if t.startswith(">"):
        return t[1:].strip()
    m = re.match(r"^(cmd|shell|terminal|run command)[:\s]+(.+)$", t, re.I)
    return m.group(2).strip() if m else None


class Shell:
    def __init__(self, start: str | None = None):
        self.cwd = str(Path(start or Path.home()))

    def run(self, cmd: str) -> str:
        cmd = cmd.strip()
        if not cmd:
            return ""
        m = re.match(r"^cd(?:\s+/d)?\s*(.*)$", cmd, re.I)
        if m and "&" not in cmd:
            target = m.group(1).strip().strip('"')
            if not target:
                return self.cwd
            new = Path(target) if Path(target).is_absolute() else Path(self.cwd) / target
            try:
                new = new.resolve()
            except OSError:
                return "The system cannot find the path specified."
            if new.is_dir():
                self.cwd = str(new)
                return self.cwd
            return "The system cannot find the path specified."
        if os.name == "nt":
            argv = ["cmd", "/d", "/c", cmd]
        else:                                         # only used by the tests on Linux
            argv = ["bash", "-c", cmd]
        try:
            r = subprocess.run(argv, cwd=self.cwd, capture_output=True, timeout=TIMEOUT, creationflags=_NOWIN,
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return f"[stopped: the command ran longer than {TIMEOUT} seconds]"
        except Exception as e:
            return f"[could not run: {e}]"
        raw = (r.stdout or b"") + (r.stderr or b"")
        for enc in ("utf-8", "mbcs" if os.name == "nt" else "latin-1"):
            try:
                out = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            out = raw.decode("utf-8", "replace")
        out = out.replace("\r\n", "\n").strip("\n")
        if len(out) > MAX_OUT:
            out = out[:MAX_OUT] + "\n[output cut]"
        return out or f"[done, exit code {r.returncode}]"
