"""
core/env_file.py
------------------
Edits keys in the project's .env file in place, so Settings can change the
AI provider / API key / email account without anyone opening the file by
hand. Keeps every other line (comments, commented-out examples, other
keys) exactly as it was; only the active `KEY=...` line for each key
touched is rewritten, or appended if there isn't one yet. os.environ is
updated too so the change is visible to anything that reads it afterward.

config.Config reads the environment once at startup, so most of these
only take effect after a restart — the Settings dialog offers one.
"""

import os
import re
from pathlib import Path

from config import APP_ROOT

ENV_PATH = APP_ROOT / ".env"


def _format(value: str) -> str:
    # Quote anything python-dotenv would otherwise cut short or mangle.
    if value == "" or re.search(r"[\s#\"'\\$]", value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def read_value(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def update_env(updates: dict[str, str | None], path: Path = ENV_PATH) -> None:
    """updates maps KEY -> new value, or KEY -> None to remove the active
    line for that key (falling back to the built-in default)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []

    remaining = dict(updates)
    out = []
    for line in lines:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        key = match.group(1) if match else None
        if key in remaining:
            value = remaining.pop(key)
            if value is not None:
                out.append(f"{key}={_format(value)}")
            continue  # None -> drop the line
        out.append(line)

    for key, value in remaining.items():
        if value is not None:
            out.append(f"{key}={_format(value)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")

    for key, value in updates.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
