"""
core/memory.py
-----------------
SQLite-backed memory store — Stage 7. Covers the categories from the
project spec: preferences, project info, custom commands, general
remembered facts, and frequently-used applications (tracked
automatically, not something the AI has to remember to do).

Conversation context itself still lives in core/brain.py's short-term
history and resets each run by design — that's the "short-term" context
from Stage 3. What's stored here is the durable stuff EV should still
know the next time it starts up.

SECURITY: this module refuses to store anything that looks like a
password, API key, or auth token/secret (see _looks_sensitive()). This
is a best-effort text filter, not a guarantee — never rely on it as the
only safeguard — but it catches the obvious cases per the project's own
rule: "Do not store passwords, API keys, private authentication tokens,
or sensitive credentials in memory."
"""

import re
import sqlite3
from collections import Counter
from math import log2
from pathlib import Path
from datetime import datetime, timezone

from config import settings

_SENSITIVE_PATTERNS = [
    re.compile(r"\bpassword\b", re.IGNORECASE),
    re.compile(r"\bapi[_\s-]?key\b", re.IGNORECASE),
    re.compile(r"\bsecret\b", re.IGNORECASE),
    re.compile(r"\btoken\b", re.IGNORECASE),
    re.compile(r"\bcredential", re.IGNORECASE),
    re.compile(r"(?:\d[ -]*?){13,19}"),  # long digit runs — card-number-shaped
]

# Word-based patterns above miss a raw key filed under an innocent label
# (e.g. remember("note", "gemini", "AQ.xxxx...")), so also look at the
# *shape* of the text: well-known key prefixes, and long high-entropy
# tokens that are almost certainly keys rather than words, paths or file names.
_KEY_SHAPES = [
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),               # Google API keys (older style)
    re.compile(r"\bAQ\.[0-9A-Za-z_\-]{20,}"),               # Google AI Studio keys (newer style)
    re.compile(r"\bsk-[0-9A-Za-z_\-]{20,}"),                # OpenAI / Anthropic style keys
    re.compile(r"\bgh[pousr]_[0-9A-Za-z]{20,}"),             # GitHub tokens
    re.compile(r"\bBearer\s+[0-9A-Za-z._\-]{20,}", re.IGNORECASE),
]

VALID_CATEGORIES = {"preference", "project", "command", "fact"}


def _entropy(text: str) -> float:
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * log2(c / n) for c in counts.values())


def _has_random_looking_token(text: str) -> bool:
    """True if `text` contains a long token that looks machine-generated
    (a key or token) rather than a word, path or file name.

    Keys and file names differ in structure, and that is what this checks:
      - file names are full of separators (_ - .); random keys have few
      - CamelCase names switch letter-case rarely; random keys switch
        constantly
      - random lowercase keys carry a high share of digits
    Well-known key formats (Google, OpenAI/Anthropic, GitHub, Bearer) are
    caught separately by _KEY_SHAPES, so this only has to catch bare keys.
    It is a best-effort heuristic — a few unusual tokens can slip through,
    which is why the AI is also told never to save credentials."""
    for raw in re.split(r"\s+", text):
        tok = raw.strip(".,;:!?()[]{}<>\"'")
        if len(tok) < 32 or not re.fullmatch(r"[A-Za-z0-9_\-\.]+", tok):
            continue
        if re.fullmatch(r"[0-9a-fA-F]{32,}", tok):
            return True  # long hex string — typical token / hash-style secret
        if sum(c in "_-." for c in tok) / len(tok) >= 0.08:
            continue  # name-like: lots of separators
        letters = [c for c in tok if c.isalpha()]
        if not letters or not any(c.isdigit() for c in tok) or _entropy(tok) < 4.0:
            continue
        mixed = any(c.isupper() for c in letters) and any(c.islower() for c in letters)
        digit_ratio = sum(c.isdigit() for c in tok) / len(tok)
        case_flips = sum(1 for a, b in zip(letters, letters[1:]) if a.isupper() != b.isupper()) / max(len(letters) - 1, 1)
        if (mixed and case_flips >= 0.3) or (not mixed and digit_ratio >= 0.15):
            return True
    return False


def _looks_sensitive(text: str) -> bool:
    return (
        any(p.search(text) for p in _SENSITIVE_PATTERNS)
        or any(p.search(text) for p in _KEY_SHAPES)
        or _has_random_looking_token(text)
    )


class MemoryStore:
    def __init__(self, db_path: str | None = None):
        # settings.db_file resolves against the project folder, so the database
        # lands in the same place no matter what folder EV AI was launched from.
        path = Path(db_path) if db_path else settings.db_file
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS app_usage (
                app_name TEXT PRIMARY KEY,
                open_count INTEGER NOT NULL DEFAULT 0,
                last_opened TEXT
            )
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # General remembered facts (preferences, project info, commands, etc.)
    # ------------------------------------------------------------------
    def remember(self, category: str, key: str, value: str) -> dict:
        category = (category or "fact").strip().lower()
        if category not in VALID_CATEGORIES:
            category = "fact"
        if _looks_sensitive(key) or _looks_sensitive(value):
            return {"error": "I won't store that — it looks like a password, key, or other sensitive credential."}

        now = datetime.now(timezone.utc).isoformat()
        key_norm = key.strip().lower()
        # Overwrite any existing entry with the same category+key rather
        # than accumulating duplicates every time the fact is restated.
        self._conn.execute("DELETE FROM memories WHERE category = ? AND key = ?", (category, key_norm))
        self._conn.execute(
            "INSERT INTO memories (category, key, value, created_at) VALUES (?, ?, ?, ?)",
            (category, key_norm, value, now),
        )
        self._conn.commit()
        return {"status": "saved", "category": category, "key": key, "value": value}

    def recall(self, category: str | None = None, key: str | None = None) -> dict:
        query = "SELECT category, key, value, created_at FROM memories WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category.strip().lower())
        if key:
            query += " AND key LIKE ?"
            params.append(f"%{key.strip().lower()}%")
        query += " ORDER BY created_at DESC"

        rows = self._conn.execute(query, params).fetchall()
        return {"memories": [
            {"category": r[0], "key": r[1], "value": r[2], "created_at": r[3]} for r in rows
        ]}

    def forget(self, key: str, category: str | None = None) -> dict:
        query = "DELETE FROM memories WHERE key = ?"
        params = [key.strip().lower()]
        if category:
            query += " AND category = ?"
            params.append(category.strip().lower())
        cur = self._conn.execute(query, params)
        self._conn.commit()
        if cur.rowcount == 0:
            return {"error": f"No memory found matching '{key}'."}
        return {"status": "forgotten", "key": key, "count": cur.rowcount}

    def clear_all(self) -> dict:
        self._conn.execute("DELETE FROM memories")
        self._conn.commit()
        return {"status": "cleared"}

    # ------------------------------------------------------------------
    # Frequently-used applications (tracked automatically)
    # ------------------------------------------------------------------
    def record_app_open(self, app_name: str) -> None:
        """Called automatically from tools/applications.py.open_application
        — tracks frequently used apps without the AI needing to think
        about it or spend a tool call on it."""
        key = app_name.strip().lower()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("""
            INSERT INTO app_usage (app_name, open_count, last_opened)
            VALUES (?, 1, ?)
            ON CONFLICT(app_name) DO UPDATE SET
                open_count = open_count + 1,
                last_opened = excluded.last_opened
        """, (key, now))
        self._conn.commit()

    def frequent_apps(self, limit: int = 5) -> dict:
        rows = self._conn.execute(
            "SELECT app_name, open_count, last_opened FROM app_usage ORDER BY open_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return {"frequent_apps": [
            {"app_name": r[0], "open_count": r[1], "last_opened": r[2]} for r in rows
        ]}

    def close(self) -> None:
        self._conn.close()
