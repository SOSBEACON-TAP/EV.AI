"""
voice/listener_thread.py
--------------------------
Runs voice listening on a background QThread so speech recognition
(which blocks) never freezes the UI. Qt signals report back to the main
thread — the main window never touches the recognizer directly, which
keeps cross-thread access safe.

Signals:
    heard_text(str)             — anything EV transcribed, wake word or not
    wake_word_detected(str)     — the command text following the wake word
    mic_error(str)              — a human-readable microphone/network problem
    listening_state_changed(bool) — whether the loop is actively listening
"""

from PySide6.QtCore import QThread, Signal

from voice.speech_to_text import SpeechToText, MicrophoneUnavailableError
from voice.wake_word import matches_wake_word, strip_wake_word


class VoiceListenerThread(QThread):
    heard_text = Signal(str)
    wake_word_detected = Signal(str)
    mic_error = Signal(str)
    listening_state_changed = Signal(bool)

    def __init__(self, wake_word: str, parent=None):
        super().__init__(parent)
        self.wake_word = wake_word
        self._stt = SpeechToText()
        self._running = False

    def run(self):
        self._running = True

        if not self._stt.check_microphone():
            self.mic_error.emit("No microphone detected.")
            return

        try:
            threshold = self._stt.calibrate(duration=1.0)
            self.heard_text.emit(f"(mic calibrated — sensitivity threshold: {threshold})")
        except MicrophoneUnavailableError as e:
            self.mic_error.emit(f"Microphone error during calibration: {e}")
            return

        self.listening_state_changed.emit(True)
        try:
            while self._running:
                try:
                    text = self._stt.listen_once(timeout=4.0, phrase_time_limit=6.0)
                except MicrophoneUnavailableError as e:
                    self.mic_error.emit(f"Microphone error: {e}")
                    break
                except TimeoutError:
                    continue  # nothing said in this window, keep looping
                except ConnectionError as e:
                    self.mic_error.emit(str(e))
                    continue  # network hiccup — keep trying

                if not self._running:
                    break
                if not text:
                    continue

                self.heard_text.emit(text)

                if matches_wake_word(text, self.wake_word):
                    command = strip_wake_word(text, self.wake_word)
                    self.wake_word_detected.emit(command)
        finally:
            self.listening_state_changed.emit(False)

    def stop(self):
        self._running = False
