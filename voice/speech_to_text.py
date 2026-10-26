"""
voice/speech_to_text.py
------------------------
Wraps the `speech_recognition` library for capturing and transcribing
speech from the default microphone.

Uses Google's free Web Speech API via SpeechRecognition — no API key
needed, but it does require an internet connection and is rate-limited
(fine for personal use; not meant for heavy/production traffic). A
later stage could swap in an offline engine (e.g. Vosk) behind this
same interface without changing any calling code.
"""

import speech_recognition as sr


class MicrophoneUnavailableError(Exception):
    """Raised when no working microphone can be found or accessed."""


class SpeechToText:
    def __init__(self, energy_threshold: int = 300, pause_threshold: float = 0.8):
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = energy_threshold
        self._recognizer.pause_threshold = pause_threshold
        self._recognizer.dynamic_energy_threshold = True

    @staticmethod
    def check_microphone() -> bool:
        """Return True if at least one microphone appears to be available."""
        try:
            return len(sr.Microphone.list_microphone_names()) > 0
        except Exception:
            return False

    def calibrate(self, duration: float = 1.0) -> int:
        """Sample ambient noise ONCE to set a sensible energy_threshold.

        Call this once when listening starts — NOT on every listen_once()
        call. Recalibrating every loop was the Stage 2 bug: repeated
        recalibration in a quiet-but-not-silent room can drift the
        threshold up until normal speech volume never crosses it, so the
        mic looks "active" but never actually catches a phrase.

        Returns the resulting energy_threshold, mainly for diagnostics —
        ui/main_window.py surfaces it so an unreasonably high value (e.g.
        a noisy room) is visible instead of silently failing.
        """
        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=duration)
        except OSError as e:
            raise MicrophoneUnavailableError(str(e)) from e
        return int(self._recognizer.energy_threshold)

    def listen_once(self, timeout: float = 4.0, phrase_time_limit: float = 6.0):
        """Listen for a single phrase and return the transcribed text.

        Returns:
            str: the transcribed text.
            None: something was heard but could not be understood.
        Raises:
            MicrophoneUnavailableError: no mic present/usable.
            TimeoutError: nothing was said within `timeout` seconds.
            ConnectionError: the recognition service was unreachable.
        """
        try:
            with sr.Microphone() as source:
                audio = self._recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_time_limit
                )
        except OSError as e:
            raise MicrophoneUnavailableError(str(e)) from e
        except sr.WaitTimeoutError as e:
            raise TimeoutError("No speech detected") from e

        try:
            return self._recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None  # heard something, couldn't make out words
        except sr.RequestError as e:
            raise ConnectionError(f"Speech recognition service unavailable: {e}") from e
