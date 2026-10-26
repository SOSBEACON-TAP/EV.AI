"""
core/log_buffer.py
--------------------
Keeps an in-memory copy of everything EV.AI prints — startup messages,
Observation/Video mode status lines, tool errors, all the "[EV AI] ..."
prints scattered through this project — so Settings -> View Log can show
the full history inside the app itself, instead of only whatever
happened to still be scrolled into view in a terminal window (or not
visible at all, if EV.AI was launched silently via pythonw.exe/autostart,
which has no console at all).

install() replaces sys.stdout/sys.stderr with a small tee that writes to
both the real stream (so a terminal, if there is one, still sees
everything as before) and this buffer. Call it once, as early as
possible — main.py does this before importing anything else, so even
import-time prints (pygame's banner, etc.) are captured.
"""

import sys
import threading
from collections import deque
from datetime import datetime

_MAX_LINES = 4000


class _LogBuffer:
    def __init__(self, max_lines: int = _MAX_LINES):
        self._lines = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def write_line(self, text: str) -> None:
        text = text.rstrip("\n")
        if not text:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self._lines.append(f"[{timestamp}] {text}")

    def get_text(self) -> str:
        with self._lock:
            return "\n".join(self._lines)


LOG = _LogBuffer()


class _TeeStream:
    """Mirrors every write() to the real stream and, line by line, into
    LOG. Buffers partial lines (print() calls write() more than once per
    line in some cases) until a newline actually arrives."""

    def __init__(self, real_stream):
        # real_stream is None under pythonw.exe (silent launch: boot.bat,
        # autostart) — there's no console, so sys.stdout/sys.stderr are
        # literally None. Plain print() tolerates that, but a tee that
        # blindly calls .write() on it raises, which used to kill the
        # startup thread on its very first print and leave the splash
        # screen stuck at 0%. So every use of the real stream is guarded,
        # and the in-memory log still works with no console at all.
        self._real = real_stream
        self._partial = ""

    def write(self, text: str) -> int:
        if self._real is not None:
            try:
                self._real.write(text)
            except Exception:
                pass  # a closed/broken console must never break the app
        self._partial += text
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            LOG.write_line(line)
        return len(text)

    def flush(self) -> None:
        if self._real is not None:
            try:
                self._real.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return bool(getattr(self._real, "isatty", lambda: False)())


def install() -> None:
    """Call once, before any other project module is imported, so
    startup prints are captured too. Safe to call more than once —
    won't double-wrap an already-installed tee."""
    if not isinstance(sys.stdout, _TeeStream):
        sys.stdout = _TeeStream(sys.stdout)
    if not isinstance(sys.stderr, _TeeStream):
        sys.stderr = _TeeStream(sys.stderr)
