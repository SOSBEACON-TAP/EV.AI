"""
core/personality.py
---------------------
How EV AI sounds. A personality changes tone and style only — it never
changes what EV is allowed to do (tool confirmations are enforced in code,
same as for conversational modes in core/modes.py). Read fresh on every
request, so switching in Settings applies to the very next reply.
"""

from core import user_prefs

PERSONALITIES = {
    "default": ("Default", ""),
    "professional": ("Professional",
                     "\n\nPersonality: professional. Be polished, precise and businesslike. "
                     "No slang, no emoji, no jokes. Lead with the answer, keep it organised."),
    "friendly": ("Friendly",
                 "\n\nPersonality: friendly. Be warm, upbeat and encouraging, like a helpful friend. "
                 "Use a relaxed tone and the occasional light touch of enthusiasm, but stay concise."),
    "humorous": ("Humorous",
                 "\n\nPersonality: humorous. Be witty and playful with light, good-natured jokes, "
                 "but never at the cost of clarity — the actual answer must still be correct and easy to find. "
                 "Keep jokes short and skip them for serious or urgent topics."),
}


def current() -> str:
    key = user_prefs.get("personality")
    return key if key in PERSONALITIES else "default"


def prompt_addition() -> str:
    return PERSONALITIES[current()][1]
