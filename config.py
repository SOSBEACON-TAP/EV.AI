"""
config.py
---------
Central configuration for EV AI.

Loads settings from a `.env` file (see `.env.example`) using python-dotenv.
NEVER hard-code API keys or secrets in this file — they belong in `.env`,
which should be added to your .gitignore and never committed.
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
from app_version import VERSION as _APP_VERSION


def _app_root() -> Path:
    """Where user data (.env, database/, data/) lives.

    Running from source, that's this file's folder, same as always. But
    once packaged with PyInstaller (Stage 10), `__file__` would resolve
    inside the temporary folder PyInstaller unpacks itself into at
    startup (sys._MEIPASS) — writable, but wiped the moment the app
    exits. Anything meant to persist across runs (the memory database,
    WhatsApp/browser login sessions, your real .env) has to live next to
    the actual .exe instead, which is sys.executable's folder once
    frozen. Bundled read-only app resources (ui/styles/dark_theme.qss)
    are a different concern — see resource_path() in main.py.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT = _app_root()

# Load variables from a local .env file (if present) into the process env.
load_dotenv(APP_ROOT / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


# Where "Check for updates" looks for a newer version (a version.json you host —
# see scripts/make_release.py). Put YOUR address here before you publish, so every
# copy you hand out checks it automatically; users can still override it with
# UPDATE_CHECK_URL in .env. Leave empty to turn update checking off.
# Example: "https://raw.githubusercontent.com/YOURNAME/ev-ai/main/version.json"
DEFAULT_UPDATE_CHECK_URL = ""


# Providers that speak the OpenAI "chat completions" API, so one code path
# in core/brain.py serves all of them (ChatGPT/OpenAI, OpenRouter, DeepSeek,
# Mistral, xAI Grok, and "custom" = any OpenAI-compatible server such as
# Ollama or LM Studio, via AI_BASE_URL). Groq is handled separately.
# provider -> (base_url or None for OpenAI itself, default model,
#              default vision model, provider-specific key env var)
OPENAI_COMPATIBLE = {
    "openai":     (None, "gpt-4o", "gpt-4o", "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-4o", "openai/gpt-4o", "OPENROUTER_API_KEY"),
    "deepseek":   ("https://api.deepseek.com", "deepseek-chat", "deepseek-chat", "DEEPSEEK_API_KEY"),
    "mistral":    ("https://api.mistral.ai/v1", "mistral-large-latest", "pixtral-large-latest", "MISTRAL_API_KEY"),
    "xai":        ("https://api.x.ai/v1", "grok-4", "grok-4", "XAI_API_KEY"),
    "custom":     ("", "", "", ""),
}


@dataclass
class Config:
    # --- App identity ---
    APP_NAME: str = "EV.AI"
    APP_VERSION: str = _APP_VERSION
    # Optional: URL of a small version file for Settings -> Check for updates.
    UPDATE_CHECK_URL: str = field(default_factory=lambda: os.getenv("UPDATE_CHECK_URL", DEFAULT_UPDATE_CHECK_URL))

    # --- AI provider (used from Stage 3 onward) ---
    AI_PROVIDER: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "anthropic"))
    AI_API_KEY: str = field(default_factory=lambda: (
        os.getenv("AI_API_KEY")
        # Fallback so a provider-specific env var (e.g. from a provider's own
        # quickstart docs) works too, without needing AI_API_KEY set as well.
        or os.getenv({"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY",
                      "anthropic": "ANTHROPIC_API_KEY",
                      **{k: v[3] for k, v in OPENAI_COMPATIBLE.items()},
                      }.get(os.getenv("AI_PROVIDER", "anthropic").lower(), ""))
        or ""
    ))
    # Only for AI_PROVIDER=custom (or to override another OpenAI-style
    # provider's address), e.g. http://localhost:11434/v1 for Ollama.
    AI_BASE_URL: str = field(default_factory=lambda: os.getenv("AI_BASE_URL", ""))
    AI_MODEL: str = field(default_factory=lambda: os.getenv(
        "AI_MODEL",
        {
            "gemini": "gemini-3.8-flash",
            "groq": "openai/gpt-oss-120b",
            **{k: v[1] for k, v in OPENAI_COMPATIBLE.items()},
        }.get(os.getenv("AI_PROVIDER", "anthropic").lower(), "claude-sonnet-4-6"),
    ))
    # Not every text model is also vision-capable (notably on Groq), so
    # Observation mode uses its own model setting rather than reusing AI_MODEL.
    AI_VISION_MODEL: str = field(default_factory=lambda: os.getenv(
        "AI_VISION_MODEL",
        {
            "gemini": "gemini-3.8-flash",
            # meta-llama/llama-4-scout-17b-16e-instruct was decommissioned by
            # Groq (this is what caused the "AI service error (404)" in
            # Observation mode) — qwen/qwen3.8-27b is Groq's current
            # vision-capable model.
            "groq": "qwen/qwen3.8-27b",
            **{k: v[2] for k, v in OPENAI_COMPATIBLE.items()},
        }.get(os.getenv("AI_PROVIDER", "anthropic").lower(), "claude-sonnet-4-6"),
    ))

    # --- Voice (used from Stage 2 onward) ---
    WAKE_WORD: str = field(default_factory=lambda: os.getenv("WAKE_WORD", "hey ev"))
    VOICE_ENABLED: bool = field(default_factory=lambda: _get_bool("VOICE_ENABLED", False))
    TTS_VOICE: str = field(default_factory=lambda: os.getenv("TTS_VOICE", "female"))

    # --- Text-to-speech backend ---
    # "pyttsx3" (default, offline, robotic-sounding SAPI5 voice) or
    # "edge" (natural Microsoft Edge neural voice, free, no key needed).
    # Falls back to pyttsx3 automatically if "edge" is misconfigured or a
    # call to it fails.
    TTS_PROVIDER: str = field(default_factory=lambda: os.getenv("TTS_PROVIDER", "pyttsx3"))

    # Used when TTS_PROVIDER=edge — free Microsoft Edge neural voice, no
    # API key or account needed. "rate" slows/speeds speech, e.g. "-10%".
    EDGE_TTS_VOICE: str = field(default_factory=lambda: os.getenv("EDGE_TTS_VOICE", "en-US-JennyNeural"))
    EDGE_TTS_RATE: str = field(default_factory=lambda: os.getenv("EDGE_TTS_RATE", "-5%"))

    # --- UI ---
    UI_REFRESH_MS: int = field(default_factory=lambda: _get_int("UI_REFRESH_MS", 1000))
    UI_THEME: str = field(default_factory=lambda: os.getenv("UI_THEME", "dark"))

    # --- Database ---
    DB_PATH: str = field(default_factory=lambda: os.getenv("DB_PATH", "database/memory.db"))

    # --- Email (Stage 9: send_email tool) ---
    # Gmail (or any SMTP-over-SSL provider) via an App Password, not your
    # normal account password — see .env.example for how to generate one.
    EMAIL_ADDRESS: str = field(default_factory=lambda: os.getenv("EMAIL_ADDRESS", ""))
    EMAIL_APP_PASSWORD: str = field(default_factory=lambda: os.getenv("EMAIL_APP_PASSWORD", ""))
    EMAIL_SMTP_HOST: str = field(default_factory=lambda: os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com"))
    EMAIL_SMTP_PORT: int = field(default_factory=lambda: _get_int("EMAIL_SMTP_PORT", 465))

    # --- WhatsApp (Stage 9: send_whatsapp_message tool) ---
    # Browser automation against WhatsApp Web via Playwright, since there's
    # no official sending API. Keeps its own persistent browser profile
    # folder so you only scan the WhatsApp QR code once.
    WHATSAPP_PROFILE_DIR: str = field(default_factory=lambda: os.getenv("WHATSAPP_PROFILE_DIR", "data/whatsapp_profile"))

    # --- General browser control (Stage 9: tools/web_browser.py) ---
    # Separate persistent profile from WhatsApp's, so a generic "search
    # google for X" / "click Y" / "go back" session stays logged into
    # whatever sites you sign into there, independent of WhatsApp Web.
    BROWSER_PROFILE_DIR: str = field(default_factory=lambda: os.getenv("BROWSER_PROFILE_DIR", "data/browser_profile"))

    # --- Face check on startup (Stage 10: core/face_auth.py) ---
    # When true, EV AI looks at the webcam on launch and only opens if it
    # recognizes the enrolled owner — otherwise it quits instead of
    # opening. Off by default so a fresh install isn't locked before
    # enrollment (run scripts/enroll_face.py once, then flip this on).
    FACE_AUTH_ENABLED: bool = field(default_factory=lambda: _get_bool("FACE_AUTH_ENABLED", False))
    FACE_MODEL_DIR: str = field(default_factory=lambda: os.getenv("FACE_MODEL_DIR", "data/face_auth"))
    # LBPH confidence is a *distance* — lower means a closer match, not a
    # percentage. ~70 is a forgiving default; lower it for stricter
    # matching if a stranger is getting through, raise it if you keep
    # getting rejected yourself in bad lighting.
    FACE_CONFIDENCE_THRESHOLD: float = field(default_factory=lambda: float(os.getenv("FACE_CONFIDENCE_THRESHOLD", "70")))
    # How long to keep looking for a recognized face before giving up and
    # closing, in seconds.
    FACE_AUTH_TIMEOUT: float = field(default_factory=lambda: float(os.getenv("FACE_AUTH_TIMEOUT", "8")))

    # --- Safety ---
    # When True, every "sensitive" tool action requires explicit user confirmation
    # before it is executed. This should stay True in normal use.
    REQUIRE_CONFIRMATION: bool = field(default_factory=lambda: _get_bool("REQUIRE_CONFIRMATION", True))

    @property
    def db_file(self) -> Path:
        """Absolute path to the memory database. A relative DB_PATH is
        resolved against APP_ROOT (the project folder when running from
        source, or the folder next to the .exe once packaged — see
        _app_root() above), not the current working directory, so it
        lands in the same place however EV AI is launched."""
        p = Path(self.DB_PATH)
        return p if p.is_absolute() else APP_ROOT / p

    @property
    def whatsapp_profile_path(self) -> Path:
        """Absolute path to the persistent browser profile used for
        WhatsApp Web, resolved the same way as db_file."""
        p = Path(self.WHATSAPP_PROFILE_DIR)
        return p if p.is_absolute() else APP_ROOT / p

    @property
    def browser_profile_path(self) -> Path:
        """Absolute path to the general-purpose browser-control profile,
        resolved the same way as db_file/whatsapp_profile_path."""
        p = Path(self.BROWSER_PROFILE_DIR)
        return p if p.is_absolute() else APP_ROOT / p

    @property
    def face_model_path(self) -> Path:
        """Absolute path to the folder holding the trained face-recognition
        model, resolved the same way as db_file."""
        p = Path(self.FACE_MODEL_DIR)
        return p if p.is_absolute() else APP_ROOT / p

    def validate(self) -> list[str]:
        """Return a list of human-readable warnings about missing/odd config.
        Does not raise — EV AI should start even with incomplete config and
        just degrade gracefully (e.g. AI features disabled)."""
        warnings = []
        if not self.AI_API_KEY:
            warnings.append(
                "No AI_API_KEY set — EV's AI brain will be disabled until Stage 3 setup."
            )
        if self.WAKE_WORD.strip() == "":
            warnings.append("WAKE_WORD is empty — falling back to 'hey ev'.")
            self.WAKE_WORD = "hey ev"
        return warnings


# Single shared config instance used across the app
settings = Config()
