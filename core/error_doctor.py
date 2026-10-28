"""
core/error_doctor.py
----------------------
Error Doctor: checks the common things that go wrong with EV AI and says,
in plain words, how to fix each. Two parts:
  * run_checks()   - looks at this PC right now (packages, key, internet, camera, folders)
  * scan_log(text) - recognises known error messages in EV's own log

Every result is (level, title, advice) with level "ok", "warn" or "bad".
Nothing here changes anything; it only reports.
"""

import re
import socket
import sys
from importlib import metadata

from config import APP_ROOT, settings

OK, WARN, BAD = "ok", "warn", "bad"


FROZEN = bool(getattr(sys, "frozen", False))

# pip name -> import name, used when EV AI runs as the standalone .exe (packages are
# bundled inside it, so there is no pip metadata to look at).
_IMPORT_NAMES = {"opencv-contrib-python": "cv2"}


def _pkg(name: str):
    if FROZEN:
        import importlib.util
        try:
            found = importlib.util.find_spec(_IMPORT_NAMES.get(name, name)) is not None
        except (ImportError, ValueError):
            found = False
        return "bundled" if found else None
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _adapt(advice: str) -> str:
    """The pip/venv commands only make sense for the Python version of EV AI."""
    if not FROZEN or "venv\\Scripts" not in advice:
        return advice
    if "playwright" in advice:
        return ("WhatsApp / browser automation needs a Chromium download that the standalone app doesn't "
                "include yet. Use the Python version of EV AI for that feature for now.")
    return ("This package is built into the standalone app, so it can't be fixed with pip. "
            "Update EV AI (Settings → Check for updates) or download the latest release again.")


# (regex, level, title, advice) — first match per title wins, newest log lines first.
_LOG_RULES = [
    (r"CameraReservedByAnotherApp|Could not open the webcam|webcam stopped sending",
     BAD, "The webcam is busy or unplugged",
     "Close any app using the camera (Teams, Zoom, the Camera app, a browser tab). EV's tray menu has "
     "'Release camera'. Then turn Video mode off and on again."),
    (r"No module named '([\w\.]+)'",
     BAD, "A Python package is missing",
     "Open PowerShell in the EV_AI folder and run:  venv\\Scripts\\python.exe -m pip install -r requirements.txt"),
    (r"older mediapipe|mediapipe 0\.10\.31|has no attribute 'solutions'",
     BAD, "mediapipe is too new for hand tracking",
     "Run:  venv\\Scripts\\python.exe -m pip uninstall mediapipe -y   then   "
     "venv\\Scripts\\python.exe -m pip install mediapipe==0.10.21"),
    (r"\b401\b|invalid api key|incorrect api key|authentication|permission_denied|API key not valid",
     BAD, "The AI key was rejected",
     "Open Settings → Open account settings and paste a valid API key for the chosen provider."),
    (r"\b429\b|rate limit|quota|RESOURCE_EXHAUSTED",
     WARN, "AI usage limit reached",
     "Wait a minute and try again, or switch to another model/provider in account settings."),
    (r"getaddrinfo failed|Connection error|Name or service not known|Max retries exceeded|timed out",
     WARN, "Network problem",
     "Check your internet connection. EV can still handle simple commands offline "
     "(Settings → Behaviour → handle simple commands without the AI)."),
    (r"playwright|Executable doesn't exist|BrowserType\.launch",
     WARN, "WhatsApp / browser automation isn't set up",
     "Run:  venv\\Scripts\\python.exe -m playwright install chromium"),
    (r"PermissionError|Permission denied|Access is denied",
     WARN, "A file or folder wasn't allowed",
     "Move EV_AI out of protected folders (Program Files) and don't run it as a different user; "
     "close anything that has the file open."),
    (r"pycaw|comtypes",
     WARN, "Exact volume control isn't available",
     "Run:  venv\\Scripts\\python.exe -m pip install pycaw comtypes   (without it, volume uses the volume keys)."),
]

_HARMLESS = [
    (r"QFont::setPointSize: Point size <= 0", "Harmless font-size warning from Qt."),
    (r"QThread: Destroyed while thread", "Harmless message when closing EV (a helper thread was still ending)."),
    (r"QWindowsWindow::setGeometry", "Harmless window-size warning from Windows."),
]


def scan_log(text: str) -> list[tuple]:
    results, seen = [], set()
    lines = (text or "").splitlines()[-400:]
    blob = "\n".join(reversed(lines))
    for pattern, level, title, advice in _LOG_RULES:
        match = re.search(pattern, blob, re.IGNORECASE)
        if match and title not in seen:
            seen.add(title)
            extra = ""
            if match.groups():
                extra = f" (missing: {match.group(1)})"
            results.append((level, title + extra, _adapt(advice)))
    for pattern, note in _HARMLESS:
        if re.search(pattern, blob):
            results.append((OK, "Ignorable message in the log", note))
            break
    return results


def _check_python():
    v = sys.version_info
    if v < (3, 10):
        return (BAD, f"Python {v.major}.{v.minor} is too old", "Install Python 3.10 or newer and re-create the venv.")
    if FROZEN:
        return (OK, "Standalone app (Python is built in)", "")
    return (OK, f"Python {v.major}.{v.minor}.{v.micro}", "")


def _check_packages():
    out = []
    required = (("PySide6", "PySide6"), ("opencv-contrib-python", "opencv-contrib-python"),
                ("numpy", "numpy"), ("pyautogui", "pyautogui"))
    missing = [n for n, key in required if _pkg(key) is None]
    if missing:
        out.append((BAD, "Missing packages: " + ", ".join(missing),
                    _adapt("Run:  venv\\Scripts\\python.exe -m pip install -r requirements.txt")))
    else:
        out.append((OK, "Core packages installed", ""))
    mp = _pkg("mediapipe")
    if mp is None:
        out.append((WARN, "mediapipe not installed (Video mode / gestures won't work)",
                    _adapt("Run:  venv\\Scripts\\python.exe -m pip install mediapipe==0.10.21")))
    elif mp != "bundled" and tuple(int(x) for x in re.findall(r"\d+", mp)[:3]) >= (0, 10, 31):
        out.append((BAD, f"mediapipe {mp} is too new for hand tracking",
                    "Run:  venv\\Scripts\\python.exe -m pip uninstall mediapipe -y   then   "
                    "venv\\Scripts\\python.exe -m pip install mediapipe==0.10.21"))
    else:
        out.append((OK, f"mediapipe {mp}", ""))
    if sys.platform == "win32":
        if _pkg("pycaw") is None or _pkg("comtypes") is None:
            out.append((WARN, "pycaw/comtypes not installed (gesture volume uses volume keys)",
                        _adapt("Run:  venv\\Scripts\\python.exe -m pip install pycaw comtypes")))
        else:
            out.append((OK, "Exact volume control available", ""))
    return out


def _check_ai():
    if not settings.AI_API_KEY:
        return (BAD, "No AI key is set",
                "Open Settings → Open account settings, pick a provider and paste your API key.")
    return (OK, f"AI key set ({settings.AI_PROVIDER})", "")


def _check_internet():
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=2.5).close()
        return (OK, "Internet reachable", "")
    except OSError:
        return (WARN, "No internet connection",
                "Check Wi-Fi/cable. AI replies, search and updates need internet.")


def _check_camera(video_mode_on: bool):
    if video_mode_on:
        return (OK, "Camera is in use by Video mode", "")
    try:
        import cv2
    except ImportError:
        return (WARN, "Camera not checked (opencv missing)", "")
    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(0)
    try:
        if cam.isOpened():
            return (OK, "Webcam can be opened", "")
        return (WARN, "Webcam can't be opened",
                "Close other apps using it (tray menu → Release camera), check Windows privacy settings "
                "→ Camera → allow desktop apps, and that it's plugged in.")
    finally:
        cam.release()


def _check_folders():
    try:
        probe = APP_ROOT / "data"
        probe.mkdir(exist_ok=True)
        test = probe / ".write_test"
        test.write_text("ok")
        test.unlink()
        return (OK, "Data folder is writable", "")
    except OSError as e:
        return (BAD, "EV can't write to its data folder",
                f"{e}. Move EV_AI to a normal folder such as Downloads or Documents.")


def run_checks(video_mode_on: bool = False, log_text: str = "") -> list[tuple]:
    results = [_check_python()]
    results += _check_packages()
    results += [_check_ai(), _check_internet(), _check_camera(video_mode_on), _check_folders()]
    results += scan_log(log_text)
    return results


def format_report(results: list[tuple]) -> str:
    icon = {OK: "[ OK ]", WARN: "[WARN]", BAD: "[FIX ]"}
    lines = []
    for level, title, advice in results:
        lines.append(f"{icon[level]} {title}")
        if advice:
            lines.append(f"       → {advice}")
    return "\n".join(lines)
