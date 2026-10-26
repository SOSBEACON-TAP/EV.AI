"""
core/focus_match.py
---------------------
The "what should Focus Mode block?" rules, kept free of Qt so they can be
tested from a terminal (scripts/test_focus.py).

Two kinds of distraction are recognised, using the window you are looking at:
  * a BROWSER tab - the browser's window title mentions a blocked site
    (YouTube, Scratch, Discord on the web ...). Works whatever the browser
    profile name added to the end of the title. Search-result pages
    ("youtube - Google Search") are left alone.
  * a DESKTOP APP - the program's name contains a blocked word
    (Discord.exe, Scratch 3.exe ...).
Only the window title and program name are looked at, never page contents.
"""

import os
import re
import sys

BROWSERS = {"chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "chromium", "arc", "iexplore"}
_SEARCH_PAGE = re.compile(r"google search|bing$|- bing|duckduckgo|yahoo search|search results", re.I)


def parse_blocked(text: str) -> list[str]:
    """'youtube, scratch.mit.edu; discord' -> ['youtube', 'scratch', 'discord']."""
    out = []
    for raw in re.split(r"[,\n;]", text or ""):
        word = raw.strip().lower()
        word = re.sub(r"^https?://", "", word).replace("www.", "")
        if not word:
            continue
        if "." in word:
            first = word.split(".")[0]
            word = first if len(first) >= 3 else word
        out.append(word)
    return out


def active_window():
    """(hwnd, title, program) of the window in front, or None (non-Windows / failure)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return None                       # never act on EV's own windows
        import psutil
        program = psutil.Process(pid.value).name()
        return hwnd, buf.value, program
    except Exception:
        return None


def decide(title: str, program: str, blocked: list[str]):
    """Returns ("tab", site), ("app", site) or None."""
    if not blocked:
        return None
    t = (title or "").lower()
    p = (program or "").lower()
    if p.endswith(".exe"):
        p = p[:-4]
    if p in BROWSERS:
        if not t or _SEARCH_PAGE.search(t):
            return None
        for site in blocked:
            if re.search(rf"(?<![a-z0-9]){re.escape(site)}(?![a-z0-9])", t):
                return ("tab", site)
        return None
    squeezed = p.replace(" ", "").replace("-", "").replace("_", "")
    for site in blocked:
        if len(site) >= 3 and site.replace(" ", "") in squeezed:
            return ("app", site)
    return None
