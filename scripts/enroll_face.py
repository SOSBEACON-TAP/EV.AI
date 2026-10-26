"""
scripts/enroll_face.py
-----------------------
Run this once, interactively, to register your face so EV AI only opens
for you:

    venv\\Scripts\\python.exe scripts\\enroll_face.py

Look straight at your webcam and slowly turn your head left/right/up/
down while it captures — that variety is what lets it recognize you
later under slightly different angles and lighting. Takes about 20-30
seconds.

Afterward, set FACE_AUTH_ENABLED=true in your .env file to turn the
check on. Leave it false (or re-run this script) any time you want to
re-enroll — a new enrollment simply overwrites the old one.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.face_auth import enroll_owner  # noqa: E402


def _print_progress(current: int, total: int) -> None:
    bar_len = 30
    filled = int(bar_len * current / total)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\r[{bar}] {current}/{total}", end="", flush=True)


def main() -> int:
    print("EV AI — face enrollment")
    print("Look at your webcam. A window isn't shown — just look toward it and")
    print("slowly move your head slightly left, right, up, and down.\n")
    input("Press Enter when you're ready...")
    print()

    result = enroll_owner(progress_callback=_print_progress)
    print()

    if "error" in result:
        print(f"Enrollment failed: {result['error']}")
        return 1

    print(f"Done — enrolled '{result['name']}' from {result['samples']} photos.")
    print("Set FACE_AUTH_ENABLED=true in your .env file to turn the startup check on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
