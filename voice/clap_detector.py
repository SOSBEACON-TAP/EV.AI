"""
voice/clap_detector.py
------------------------
Lightweight, always-on clap detector. Unlike full voice listening (which
uses SpeechRecognition + Google's API), this reads raw microphone audio
directly via PyAudio and just watches for two sharp volume spikes close
together (a "double clap") — no internet connection or speech-API quota
used. It runs continuously in the background so EV AI can be woken up
hands-free without saying "Hey EV" first.

Only one of ClapDetectorThread / VoiceListenerThread should hold the
microphone at a time — ui/main_window.py stops this thread before
starting the wake-word listener, and restarts it once voice listening
is turned back off.
"""

import time

from PySide6.QtCore import QThread, Signal

try:
    import pyaudio
    _PYAUDIO_AVAILABLE = True
except ImportError:
    _PYAUDIO_AVAILABLE = False

try:
    import audioop

    def _rms(data: bytes) -> int:
        return audioop.rms(data, 2)
except ImportError:
    # audioop was removed from the standard library in Python 3.13+.
    # Pure-Python fallback so clap detection still works without it.
    import struct

    def _rms(data: bytes) -> int:
        count = len(data) // 2
        if count == 0:
            return 0
        samples = struct.unpack(f"<{count}h", data)
        return int((sum(s * s for s in samples) / count) ** 0.5)


class ClapDetectorThread(QThread):
    clap_detected = Signal()
    mic_error = Signal(str)

    def __init__(self, threshold: int = 4000, min_gap: float = 0.15,
                 max_gap: float = 0.6, parent=None):
        super().__init__(parent)
        self.threshold = threshold   # RMS amplitude a clap must exceed
        self.min_gap = min_gap       # shortest allowed time between the 2 claps
        self.max_gap = max_gap       # longest allowed time between the 2 claps
        self._running = False

    def run(self):
        if not _PYAUDIO_AVAILABLE:
            self.mic_error.emit("PyAudio not installed.")
            return

        self._running = True
        pa = None
        stream = None
        chunk = 1024
        rate = 44100

        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16, channels=1, rate=rate,
                input=True, frames_per_buffer=chunk,
            )
        except Exception as e:
            self.mic_error.emit(f"Could not open microphone for clap detection: {e}")
            self._cleanup(pa, stream)
            return

        last_spike_time = None
        cooldown_until = 0.0

        while self._running:
            try:
                data = stream.read(chunk, exception_on_overflow=False)
            except Exception:
                break

            volume = _rms(data)
            now = time.monotonic()

            if volume >= self.threshold and now >= cooldown_until:
                if last_spike_time is not None and self.min_gap <= (now - last_spike_time) <= self.max_gap:
                    self.clap_detected.emit()
                    last_spike_time = None
                    cooldown_until = now + 1.0  # don't re-trigger on the same noise
                else:
                    last_spike_time = now

            if last_spike_time is not None and (now - last_spike_time) > self.max_gap:
                last_spike_time = None  # first clap went stale, forget it

        self._cleanup(pa, stream)

    def _cleanup(self, pa, stream):
        try:
            if stream is not None:
                stream.stop_stream()
                stream.close()
        except Exception:
            pass
        try:
            if pa is not None:
                pa.terminate()
        except Exception:
            pass

    def stop(self):
        self._running = False
