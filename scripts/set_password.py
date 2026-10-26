"""
scripts/set_password.py
------------------------
Run this once, interactively, to set the password EV AI's startup
screen will accept as a fallback — if the face scan doesn't recognize
you (bad lighting, a new haircut, no webcam, etc.), you can type this
password instead of being locked out:

    venv\\Scripts\\python.exe scripts\\set_password.py

Re-run any time to change the password; a new one simply overwrites the
old one. This has nothing to do with FACE_AUTH_ENABLED — the fallback is
only ever offered when a face check has actually been attempted and
failed, never used in place of it.
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.face_auth import set_password  # noqa: E402


def main() -> int:
    print("EV AI — set startup password fallback")
    print("This is only ever asked for if the face scan fails to recognize you.\n")

    password = getpass.getpass("New password (min 4 characters): ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords didn't match — nothing was changed.")
        return 1

    result = set_password(password)
    if "error" in result:
        print(f"Couldn't set password: {result['error']}")
        return 1

    print("Done — this password will now work as a fallback on the startup screen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
