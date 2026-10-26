"""
core/personal_store.py
------------------------
Small JSON-backed store for things that must survive a restart: to-dos,
notes, and pending reminders. data/personal.json, written atomically.
Never raises on a missing/corrupt file — that just means "empty".
"""

import json
import os
import threading
import time

from config import APP_ROOT

_PATH = APP_ROOT / "data" / "personal.json"
_LOCK = threading.RLock()
_EMPTY = {"next_id": 1, "todos": [], "notes": [], "reminders": []}


def _load() -> dict:
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            merged = {k: (data.get(k) if isinstance(data.get(k), type(v)) else type(v)()) for k, v in _EMPTY.items()}
            merged["next_id"] = data.get("next_id") if isinstance(data.get("next_id"), int) else 1
            return merged
    except (OSError, ValueError):
        pass
    return {"next_id": 1, "todos": [], "notes": [], "reminders": []}


def _save(data: dict) -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _PATH)
    except OSError as e:
        print(f"[EV AI] Couldn't save personal data: {e}")


def add(kind: str, **fields) -> dict:
    """Append an item to todos/notes/reminders and return it (with its id)."""
    with _LOCK:
        data = _load()
        item = {"id": data["next_id"], "created": time.time(), **fields}
        data["next_id"] += 1
        data[kind].append(item)
        _save(data)
        return item


def items(kind: str) -> list[dict]:
    with _LOCK:
        return list(_load()[kind])


def update(kind: str, item_id: int, **fields) -> bool:
    with _LOCK:
        data = _load()
        for item in data[kind]:
            if item["id"] == item_id:
                item.update(fields)
                _save(data)
                return True
    return False


def remove(kind: str, item_id: int) -> bool:
    with _LOCK:
        data = _load()
        before = len(data[kind])
        data[kind] = [i for i in data[kind] if i["id"] != item_id]
        if len(data[kind]) != before:
            _save(data)
            return True
    return False
