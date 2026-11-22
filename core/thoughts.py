"""
core/thoughts.py
------------------
Thought Stream: a short live log of what EV is doing and why ("planning", "about to run...", "done", "asked you first").
Kept in memory only (nothing is written to disk) and capped at 200 lines. Shown in EV BRAIN -> Thought Stream.
"""
from __future__ import annotations

import threading
import time
from collections import deque

_LOCK = threading.Lock()
_ITEMS: deque = deque(maxlen=200)


def add(kind: str, text: str) -> None:
    """kind: 'tool' (about to run), 'done', 'fail', 'ask' (waiting for you), 'note'."""
    try:
        with _LOCK:
            _ITEMS.append({"t": time.time(), "kind": kind, "text": str(text)[:300]})
    except Exception:
        pass


def recent(n: int = 100) -> list[dict]:
    with _LOCK:
        return list(_ITEMS)[-n:]


def clear() -> None:
    with _LOCK:
        _ITEMS.clear()
