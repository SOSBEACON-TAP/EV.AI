"""
voice/wake_word.py
--------------------
Lightweight wake-word matching. Rather than a dedicated wake-word engine
(which would need a trained model — "Hey EV" isn't a built-in keyword,
and training a custom one needs a Picovoice account), Stage 2 checks each
transcribed phrase for a fuzzy match against the configured wake word.

Trade-off: simpler to set up and no external accounts, at the cost of
using more speech-recognition quota than a proper low-power wake-word
engine would (every phrase gets fully transcribed, not just spotted).
"""

import re
import difflib


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text


def matches_wake_word(heard_text: str, wake_word: str, threshold: float = 0.75) -> bool:
    """Return True if `heard_text` appears to start with the wake word.

    Checks for a direct substring match first (cheap, exact), then falls
    back to a fuzzy ratio against the leading words of the phrase, so
    mishears like "hey eve" / "a ev" still trigger reasonably.
    """
    if not heard_text:
        return False

    heard = _normalize(heard_text)
    wake = _normalize(wake_word)
    if not wake:
        return False

    if wake in heard:
        return True

    wake_word_count = len(wake.split())
    heard_words = heard.split()
    lead = " ".join(heard_words[:wake_word_count])
    ratio = difflib.SequenceMatcher(None, lead, wake).ratio()
    return ratio >= threshold


def strip_wake_word(heard_text: str, wake_word: str) -> str:
    """Remove a leading wake word from heard_text, if present, and return
    the remainder — e.g. "hey ev open youtube" -> "open youtube"."""
    heard = heard_text.strip()
    normalized_heard = _normalize(heard)
    normalized_wake = _normalize(wake_word)
    if normalized_heard.startswith(normalized_wake):
        return heard[len(wake_word):].strip(" ,.-")
    return heard
