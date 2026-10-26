"""
voice/speech_worker.py
------------------------
Runs text-to-speech on its own QThread so speaking never blocks the UI,
and so it can be interrupted (stop_speaking()) from the main thread.

Each speak() call should use a FRESH SpeechWorker instance — QThread
objects are not meant to be restarted after finishing, and pyttsx3's
COM-based engine (on Windows) should be created fresh per thread run
anyway. The main window is responsible for keeping a reference to the
current worker and letting the previous one finish before starting a
new one (see ui/main_window.py: _speak()).

Backend selection (config.settings.TTS_PROVIDER):
  - "pyttsx3" (default)  -> offline Windows SAPI5 voice, always available.
  - "edge"               -> natural Microsoft Edge neural voice via the
    free edge-tts package. No API key or account needed, just internet.
  If the selected provider is misconfigured, or the API/network call
  fails for any reason, this silently falls back to pyttsx3 for that
  utterance rather than losing speech output entirely.
"""

from PySide6.QtCore import QThread, Signal

from voice.text_to_speech import TextToSpeech
from voice.edge_tts_backend import EdgeTTS, EdgeTTSError


class SpeechWorker(QThread):
    started_speaking = Signal()
    finished_speaking = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._tts = None

    def run(self):
        self.started_speaking.emit()
        try:
            self._speak_with_fallback()
        except Exception:
            pass  # never let a TTS failure crash the app
        finally:
            self.finished_speaking.emit()

    def _speak_with_fallback(self):
        from core import voices
        choice = voices.resolve()          # follows the chosen personality

        if choice["edge"]:
            try:
                self._tts = EdgeTTS(voice=choice["voice"], rate=choice["rate"], pitch=choice["pitch"])
                self._tts.speak(self._text)
                return
            except EdgeTTSError as e:
                print(f"[EV AI] Edge TTS unavailable ({e}); "
                      f"falling back to offline voice.")
            except Exception as e:
                print(f"[EV AI] Edge TTS failed unexpectedly ({e}); "
                      f"falling back to offline voice.")

        # Default / fallback path: offline SAPI5 voice.
        self._tts = TextToSpeech(voice_gender=choice["gender"])
        self._tts.speak(self._text)

    def stop_speaking(self):
        if self._tts is not None:
            self._tts.stop()
