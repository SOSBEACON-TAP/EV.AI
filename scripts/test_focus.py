"""
Try Focus Mode's blocking rules without starting EV AI:

    venv\\Scripts\\python.exe scripts\\test_focus.py
    venv\\Scripts\\python.exe scripts\\test_focus.py "youtube, scratch, discord"

For 25 seconds it prints the window you are looking at (title + program) and what
Focus Mode would do. Click on a YouTube tab / Discord / Scratch during that time.
Nothing is closed by this script.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import user_prefs  # noqa: E402
from core.focus_match import active_window, decide, parse_blocked  # noqa: E402

CASES = [
    ("Cool video - YouTube - Google Chrome", "chrome.exe", "tab"),
    ("Cool video - YouTube - Google Chrome - Peter", "chrome.exe", "tab"),
    ("Scratch - Imagine, Program, Share - Microsoft​ Edge", "msedge.exe", "tab"),
    ("Discord | #general | My Server", "Discord.exe", "app"),
    ("Scratch 3.29", "Scratch 3.exe", "app"),
    ("youtube - Google Search - Google Chrome", "chrome.exe", None),
    ("Untitled - Notepad", "notepad.exe", None),
    ("Homework - Google Docs - Google Chrome", "chrome.exe", None),
]


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else user_prefs.get("focus_blocked")
    blocked = parse_blocked(text)
    print("Blocked words:", blocked)
    bad = 0
    for title, program, expect in CASES:
        got = decide(title, program, blocked)
        kind = got[0] if got else None
        ok = kind == expect
        bad += not ok
        print(("PASS " if ok else "FAIL ") + f"{program:14} {title!r} -> {got}")
    print("\nNow watching the window in front for 25 seconds. Switch to YouTube / Discord / Scratch...\n")
    end = time.time() + 25
    while time.time() < end:
        info = active_window()
        if info is None:
            print("(can't read the active window - is this Windows?)")
        else:
            _hwnd, title, program = info
            print(f"{program:18} {title[:70]!r:74} -> {decide(title, program, blocked)}")
        time.sleep(1.5)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
