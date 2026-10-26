"""
tools/browser.py
-------------------
Web/browser tools: open websites, search the web, open/search YouTube,
open WhatsApp Web, and manage a small set of saved bookmarks. Uses
Python's standard `webbrowser` module, which opens the user's actual
default browser — no browser automation, no new dependency.

Bookmarks are stored in a small JSON file (database/bookmarks.json) so
they persist across restarts. Stage 7 introduces the full SQLite memory
system — this stays a simple flat file until then rather than adding a
second storage mechanism early.
"""

import json
import re
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

_BOOKMARKS_PATH = Path(__file__).resolve().parent.parent / "database" / "bookmarks.json"

_DEFAULT_SITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "netflix": "https://netflix.com",
    "reddit": "https://reddit.com",
    "amazon": "https://amazon.com",
}


def _load_bookmarks() -> dict:
    if not _BOOKMARKS_PATH.exists():
        return {}
    try:
        return json.loads(_BOOKMARKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_bookmarks(bookmarks: dict) -> None:
    _BOOKMARKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _BOOKMARKS_PATH.write_text(json.dumps(bookmarks, indent=2), encoding="utf-8")


def _normalize_url(target: str) -> str:
    target = target.strip()
    if re.match(r"^https?://", target, re.IGNORECASE):
        return target
    if "." in target and " " not in target:
        return f"https://{target}"
    return f"https://{target}.com"


def open_website(target: str) -> dict:
    """Open a website. Accepts a full URL, a bare domain (e.g.
    'github.com'), a known site name (e.g. 'youtube', 'gmail'), or a
    saved bookmark name."""
    key = target.strip().lower()
    bookmarks = _load_bookmarks()

    if key in bookmarks:
        url = bookmarks[key]
    elif key in _DEFAULT_SITES:
        url = _DEFAULT_SITES[key]
    else:
        url = _normalize_url(target)

    webbrowser.open(url)
    return {"status": "opened", "url": url}


def search_web(query: str) -> dict:
    """Open a web search for `query` in the default browser."""
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    webbrowser.open(url)
    return {"status": "opened", "url": url, "query": query}


def open_youtube() -> dict:
    return open_website("youtube")


def search_youtube(query: str) -> dict:
    """Open YouTube search results for `query`."""
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    webbrowser.open(url)
    return {"status": "opened", "url": url, "query": query}


def open_whatsapp_web() -> dict:
    return open_website("whatsapp")


def add_bookmark(name: str, url: str) -> dict:
    """Save a website under a short name so it can be opened by that
    name later, e.g. add_bookmark('school portal', 'https://...')."""
    bookmarks = _load_bookmarks()
    key = name.strip().lower()
    bookmarks[key] = _normalize_url(url)
    _save_bookmarks(bookmarks)
    return {"status": "saved", "name": name, "url": bookmarks[key]}


def list_bookmarks() -> dict:
    return {"bookmarks": _load_bookmarks()}
