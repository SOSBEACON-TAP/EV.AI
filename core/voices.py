"""
core/voices.py
----------------
Which voice EV speaks with. Each personality (Professional, Friendly,
Humorous) can have its own natural Microsoft Edge voice, speaking speed and
pitch; "Default" keeps whatever voice you set in account settings.

Per-personality voices use the online Edge voices (needs internet and the
edge-tts + pygame packages). If that isn't available, speech quietly falls
back to the offline Windows voice, with a male/female pick that suits the
personality, so EV never goes silent.
"""

from config import settings
from core import user_prefs
from core.personality import current as current_personality

# (voice id, label shown in Settings)
VOICE_CHOICES = [
    ("en-US-GuyNeural", "Guy — US male, calm"),
    ("en-US-DavisNeural", "Davis — US male, casual"),
    ("en-US-AriaNeural", "Aria — US female, expressive"),
    ("en-US-JennyNeural", "Jenny — US female, friendly"),
    ("en-US-MichelleNeural", "Michelle — US female, clear"),
    ("en-GB-RyanNeural", "Ryan — UK male"),
    ("en-GB-SoniaNeural", "Sonia — UK female"),
    ("en-AU-NatashaNeural", "Natasha — Australian female"),
    ("en-IN-PrabhatNeural", "Prabhat — Indian male"),
    ("en-IN-NeerjaNeural", "Neerja — Indian female"),
]

# per personality: (pref key, speaking rate, pitch, offline gender)
STYLE = {
    "professional": ("voice_professional", "-4%", "+0Hz", "male"),
    "friendly": ("voice_friendly", "+0%", "+2Hz", "female"),
    "humorous": ("voice_humorous", "+8%", "+0Hz", "male"),
}

SAMPLES = {
    "default": "Hello, this is how I sound.",
    "professional": "Good day. Your schedule is clear and all systems are running normally.",
    "friendly": "Hey there! Great to hear from you. Ready when you are!",
    "humorous": "I would tell you a joke about my voice, but it might not be audible. Ha!",
}


def resolve(personality: str | None = None) -> dict:
    """What the speech worker should use right now:
    {"edge": bool, "voice": str, "rate": str, "pitch": str, "gender": str}"""
    key = personality or current_personality()
    provider_is_edge = (settings.TTS_PROVIDER or "").lower() == "edge"
    if key in STYLE and user_prefs.get("voice_per_personality"):
        pref_key, rate, pitch, gender = STYLE[key]
        voice = str(user_prefs.get(pref_key)) or STYLE_DEFAULT_VOICE[key]
        return {"edge": True, "voice": voice, "rate": rate, "pitch": pitch, "gender": gender}
    return {"edge": provider_is_edge, "voice": settings.EDGE_TTS_VOICE, "rate": settings.EDGE_TTS_RATE,
            "pitch": "+0Hz", "gender": settings.TTS_VOICE}


STYLE_DEFAULT_VOICE = {"professional": "en-US-GuyNeural", "friendly": "en-US-AriaNeural",
                       "humorous": "en-US-DavisNeural"}


def sample_text(personality: str | None = None) -> str:
    return SAMPLES.get(personality or current_personality(), SAMPLES["default"])
