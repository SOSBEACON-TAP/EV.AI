"""
voice/text_to_speech.py
-------------------------
Wraps pyttsx3 for offline text-to-speech (uses Windows SAPI5 voices —
no internet connection or API key required).

Voice selection: Windows ships at least two SAPI5 voices out of the box —
"Microsoft David" (male) and "Microsoft Zira" (female). This picks a
female voice by default (falls back to whatever's available if Zira
isn't installed on this machine). pyttsx3/SAPI5 doesn't expose a pitch
control, so "sweeter" mostly comes from voice choice + a slightly
higher rate.

IMPORTANT: on Windows, pyttsx3/SAPI5 uses COM, which is not safe to
share across threads. A TextToSpeech instance must be created AND used
entirely within a single worker thread — see voice/speech_worker.py,
which creates a fresh instance per thread run rather than reusing one.
"""

import pyttsx3


class TextToSpeech:
    def __init__(self, rate: int = 205, volume: float = 1.0, voice_gender: str = "female"):
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._engine.setProperty("volume", volume)
        self._apply_voice(voice_gender)

    def _apply_voice(self, voice_gender: str) -> None:
        """Pick a SAPI5 voice matching the requested gender, if one exists.
        Silently keeps the system default if nothing matches — never lets
        a missing voice crash startup."""
        if not voice_gender:
            return
        try:
            voices = self._engine.getProperty("voices")
        except Exception:
            return

        wanted = voice_gender.lower()
        for v in voices:
            name = (v.name or "").lower()
            vid = (v.id or "").lower()
            # SAPI5 voices report gender inconsistently across Windows
            # versions, so match on name/id text as the reliable signal
            # (e.g. "Zira" = female, "David"/"Mark" = male).
            female_hit = wanted == "female" and ("zira" in name or "female" in name or "female" in vid)
            male_hit = wanted == "male" and ("david" in name or "mark" in name or "male" in name or "male" in vid)
            if female_hit or male_hit:
                try:
                    self._engine.setProperty("voice", v.id)
                except Exception:
                    pass
                return

    def speak(self, text: str) -> None:
        """Speak text. Blocks the calling thread until finished or stop()
        is called from another thread."""
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        """Interrupt speech currently in progress."""
        try:
            self._engine.stop()
        except Exception:
            pass  # never let a stop() failure crash the caller
