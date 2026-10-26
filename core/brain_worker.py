"""
core/brain_worker.py
----------------------
Runs a single Brain.ask() call on a background QThread so the network
request never freezes the UI. A fresh BrainWorker is created per
request/response — the Brain instance itself (and its conversation
history) lives in the main window and is reused across calls.
"""

from PySide6.QtCore import QThread, Signal

from core.brain import Brain, BrainError


class BrainWorker(QThread):
    reply_ready = Signal(str)
    brain_error = Signal(str)

    def __init__(self, brain: Brain, user_text: str, parent=None):
        super().__init__(parent)
        self._brain = brain
        self._user_text = user_text

    def run(self):
        try:
            reply = self._brain.ask(self._user_text)
        except BrainError as e:
            self.brain_error.emit(str(e))
            return
        except Exception as e:  # never let an unexpected error crash the app
            self.brain_error.emit(f"Unexpected error: {e}")
            return
        self.reply_ready.emit(reply)


class ImageWorker(QThread):
    """One Brain.ask_about_image() call off the GUI thread."""
    reply_ready = Signal(str)
    brain_error = Signal(str)

    def __init__(self, brain: Brain, image_bytes: bytes, mime: str, question: str, label: str, parent=None):
        super().__init__(parent)
        self._args = (image_bytes, mime, question, label)
        self._brain = brain

    def run(self):
        try:
            reply = self._brain.ask_about_image(*self._args)
        except BrainError as e:
            self.brain_error.emit(str(e))
            return
        except Exception as e:
            self.brain_error.emit(f"Unexpected error: {e}")
            return
        self.reply_ready.emit(reply)
