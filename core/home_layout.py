"""
core/home_layout.py
-------------------
Which buttons show on the home screen's MODE panel and how big they are.
Edited in Settings > HOME SCREEN; applied live by ui/main_window.py.
"""

import json

from core import user_prefs

# key, label shown in Settings
BUTTONS = (
    ("normal", "Normal mode"), ("automatic", "Automatic mode"), ("serious", "Serious mode"),
    ("deep", "Deep Thinking mode"), ("observe", "Observe"), ("video", "Video (gestures)"),
    ("song", "Song"), ("focus", "Focus"), ("insights", "App Insights"), ("finder", "File Finder"),
)
SIZES = {"S": 24, "M": 30, "L": 48}
FONT = {"S": 10, "M": 11, "L": 15}


def hidden() -> set[str]:
    return {k for k in (user_prefs.get("home_hidden") or "").split(",") if k}


def set_hidden(keys: set[str]) -> None:
    user_prefs.set_value("home_hidden", ",".join(sorted(keys)))


def sizes() -> dict:
    try:
        data = json.loads(user_prefs.get("home_sizes") or "{}")
        return {k: v for k, v in data.items() if v in SIZES} if isinstance(data, dict) else {}
    except Exception:
        return {}


def size_of(key: str) -> str:
    return sizes().get(key, "M")


def set_size(key: str, size: str) -> None:
    data = sizes()
    if size == "M":
        data.pop(key, None)
    else:
        data[key] = size
    user_prefs.set_value("home_sizes", json.dumps(data))


def reset() -> None:
    user_prefs.set_value("home_hidden", "")
    user_prefs.set_value("home_sizes", "{}")
