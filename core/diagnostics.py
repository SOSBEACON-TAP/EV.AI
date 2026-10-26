"""
core/diagnostics.py
---------------------
Builds the text shown in Settings -> System & About -> Diagnostics: versions,
which optional packages are installed, a (secret-free) summary of the
configuration, and the tail of the app's own log. Safe to paste into a
bug report — API keys and passwords are never included.
"""

import platform
import sys
from importlib import metadata

from config import APP_ROOT, settings
from core import user_prefs
from core.log_buffer import LOG

_PACKAGES = ("PySide6", "anthropic", "google-genai", "groq", "openai", "mediapipe",
             "opencv-contrib-python", "pyautogui", "pyttsx3", "edge-tts", "pygame",
             "SpeechRecognition", "PyAudio", "playwright", "python-dotenv")


def _build():
    try:
        from app_version import BUILD
        return BUILD
    except Exception:
        return "?"


def _version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "not installed"


def build_report(log_lines: int = 40) -> str:
    out = [
        f"{settings.APP_NAME} {settings.APP_VERSION} (build {_build()})",
        f"Python {sys.version.split()[0]} ({sys.executable})",
        f"{platform.system()} {platform.release()} {platform.machine()}",
        f"App folder: {APP_ROOT}",
        "",
        "-- Configuration (secrets omitted) --",
        f"AI provider: {settings.AI_PROVIDER}   model: {settings.AI_MODEL}",
        f"API key set: {'yes' if settings.AI_API_KEY else 'no'}",
        f"Email set up: {'yes' if settings.EMAIL_ADDRESS and settings.EMAIL_APP_PASSWORD else 'no'}"
        f" ({settings.EMAIL_SMTP_HOST}:{settings.EMAIL_SMTP_PORT})",
        f"Voice: {settings.TTS_PROVIDER}   wake word: {settings.WAKE_WORD!r}",
        f"Face check: {'on' if settings.FACE_AUTH_ENABLED else 'off'}",
        "",
        "-- Settings --",
        *[f"{k}: {v}" for k, v in user_prefs.load().items()],
        "",
        "-- Packages --",
        *[f"{name}: {_version(name)}" for name in _PACKAGES],
        "",
        f"-- Last {log_lines} log lines --",
    ]
    lines = LOG.get_text().splitlines()[-log_lines:]
    out.extend(lines or ["(log is empty)"])
    return "\n".join(out)
