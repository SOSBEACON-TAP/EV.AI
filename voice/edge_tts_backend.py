"""
voice/edge_tts_backend.py
---------------------------
Optional TTS backend using Microsoft Edge's online neural voices via the
free `edge-tts` package (the same voices behind Edge's "Read Aloud"
feature). No API key, no account, no payment tier restrictions — just an
internet connection.

This module is designed to NEVER crash the app:
  - Any network/package/playback failure raises EdgeTTSError, which
    speech_worker.py catches and falls back to the offline pyttsx3 voice.

Good natural-sounding female voices to try for EDGE_TTS_VOICE:
  - en-US-JennyNeural   (calm, friendly)
  - en-US-AriaNeural    (warm, expressive)
  - en-US-MichelleNeural
Run `edge-tts --list-voices` (after installing) to see the full list.
"""

import asyncio
import os
import tempfile


class EdgeTTSError(Exception):
    """Raised for any edge-tts config/network/playback problem. Callers
    should catch this and fall back to the offline TTS voice."""


class EdgeTTS:
    def __init__(self, voice: str = "en-US-JennyNeural", rate: str = "-5%", pitch: str = "+0Hz"):
        if not voice:
            raise EdgeTTSError("No EDGE_TTS_VOICE configured.")
        self._voice = voice
        self._rate = rate or "+0%"
        self._pitch = pitch or "+0Hz"
        self._stopped = False
        self._mixer_ready = False

    def _ensure_mixer(self) -> None:
        if self._mixer_ready:
            return
        try:
            import pygame
        except ImportError as e:
            raise EdgeTTSError(
                "The 'pygame' package is required to play Edge TTS audio. "
                "Run: pip install pygame"
            ) from e
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        self._mixer_ready = True

    def speak(self, text: str) -> None:
        """Fetch audio for `text` from Microsoft Edge's TTS service and
        play it. Blocks the calling thread until playback finishes or
        stop() is called."""
        import pygame  # safe: _ensure_mixer() already imported/initialized it

        self._stopped = False
        self._ensure_mixer()
        audio_path = self._fetch_audio(text)
        try:
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stopped:
                    pygame.mixer.music.stop()
                    break
                pygame.time.wait(50)
        finally:
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            try:
                os.remove(audio_path)
            except OSError:
                pass

    def _fetch_audio(self, text: str) -> str:
        try:
            import edge_tts
        except ImportError as e:
            raise EdgeTTSError(
                "The 'edge-tts' package is not installed. "
                "Run: pip install edge-tts"
            ) from e

        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        async def _generate():
            communicate = edge_tts.Communicate(text, voice=self._voice, rate=self._rate, pitch=self._pitch)
            await communicate.save(path)

        try:
            asyncio.run(_generate())
        except Exception as e:
            try:
                os.remove(path)
            except OSError:
                pass
            raise EdgeTTSError(f"Edge TTS request failed: {e}") from e

        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise EdgeTTSError("Edge TTS returned no audio (check your internet connection).")

        return path

    def stop(self) -> None:
        """Interrupt speech currently in progress."""
        self._stopped = True
        if not self._mixer_ready:
            return
        try:
            import pygame
            pygame.mixer.music.stop()
        except Exception:
            pass  # never let a stop() failure crash the caller
