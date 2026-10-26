"""
core/vision_worker.py
------------------------
Runs a single Brain.observe_screen() call on a background QThread, same
pattern as BrainWorker — so a screen-observation API call never freezes
the UI. One fresh worker per screenshot.
"""

from PySide6.QtCore import QThread, Signal

from core.brain import Brain, BrainError


class VisionWorker(QThread):
    comment_ready = Signal(str)   # a non-empty comment worth speaking
    nothing_found = Signal()      # looked, nothing worth saying
    vision_error = Signal(str)

    def __init__(self, brain: Brain, image_png_bytes: bytes, parent=None):
        super().__init__(parent)
        self._brain = brain
        self._image_bytes = image_png_bytes

    def run(self):
        try:
            comment = self._brain.observe_screen(self._image_bytes)
        except BrainError as e:
            self.vision_error.emit(str(e))
            return
        except Exception as e:
            self.vision_error.emit(f"Unexpected error: {e}")
            return

        if comment:
            self.comment_ready.emit(comment)
        else:
            self.nothing_found.emit()
