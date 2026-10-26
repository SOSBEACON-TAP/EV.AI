"""
core/gesture_worker.py
-------------------------
Video mode: a background QThread that keeps the webcam open, tracks up to two
hands with MediaPipe, and hands each frame to core/gesture_engine.py, which
decides what (if anything) you just did. The worker turns the engine's events
into key presses / volume changes.

The ten gestures and their actions are listed in core/gesture_engine.py and
explained in Settings > GESTURE CONTROL. Thresholds, cooldowns and the
on/off switch are read from the saved settings (core/user_prefs.py) once a
second, so changes in Settings apply to a running session immediately.

Safety / robustness
  * Missing opencv / mediapipe / pyautogui, a busy webcam, or a too-new
    mediapipe all produce a plain-language `error` instead of a crash.
  * The loop never blocks the UI: it lives in this thread, and every
    emitted preview is throttled.
  * stop() ends the loop; the `finally` block always releases the webcam.
  * Volume uses pycaw (exact master volume) when installed, otherwise the
    keyboard volume keys.
"""

import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from core import user_prefs
from core.gesture_engine import DEFAULT_CFG, GestureEngine


class GestureWorker(QThread):
    status = Signal(str)          # short status text, e.g. "Next tab (Ctrl+Tab)"
    error = Signal(str)           # fatal — dependency missing, camera unavailable, ...
    frame_ready = Signal(object)  # dict: qimage/clean/hand/eye + state/gesture/paused

    # Preview frame-rate cap (emitting every frame floods the GUI thread).
    _PREVIEW_INTERVAL = 0.08
    # How often saved settings are re-read.
    _CFG_REFRESH = 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._last_preview_time = 0.0
        self._volume = None          # lazily created pycaw endpoint, or False if unavailable
        self._pause_request = None   # set from the UI thread: True / False / None

    # -- called from the UI thread -------------------------------------
    def stop(self) -> None:
        """Signals the loop to exit; call wait() afterward to block until
        the thread (and the camera it holds) has actually stopped."""
        self._running = False

    def set_paused(self, paused: bool) -> None:
        self._pause_request = bool(paused)

    # -- settings --------------------------------------------------------
    @staticmethod
    def _load_cfg() -> dict:
        prefs = user_prefs.load()
        return {k: prefs[k] for k in DEFAULT_CFG if k in prefs}

    # -- thread body -------------------------------------------------------
    def run(self) -> None:
        try:
            import cv2
        except ImportError:
            self.error.emit("Video mode needs opencv-contrib-python (already required for the face check).")
            return
        try:
            import mediapipe as mp
        except ImportError:
            self.error.emit("Video mode needs the mediapipe package. Run: pip install mediapipe==0.10.21")
            return
        try:
            import pyautogui
        except ImportError:
            self.error.emit("Video mode needs pyautogui. Run: pip install pyautogui")
            return
        pyautogui.PAUSE = 0
        pyautogui.FAILSAFE = False

        cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        # Speed: small MJPG frames at 30 fps, and no queue of stale frames.
        # (Each call is harmless if the camera ignores it.)
        for prop, value in ((cv2.CAP_PROP_BUFFERSIZE, 1), (cv2.CAP_PROP_FRAME_WIDTH, 640),
                            (cv2.CAP_PROP_FRAME_HEIGHT, 480), (cv2.CAP_PROP_FPS, 30)):
            cam.set(prop, value)
        cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        if not cam.isOpened():
            cam.release()
            self.error.emit(
                "Could not open the webcam. Close any other app using it "
                "(Teams, Zoom, the Camera app) and try again.")
            return

        # mediapipe 0.10.31 removed the legacy mp.solutions API used here;
        # requirements.txt pins 0.10.21. Catch a newer install politely.
        try:
            hands = mp.solutions.hands.Hands(
                model_complexity=0,
                max_num_hands=2,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )
            drawing_utils = mp.solutions.drawing_utils
            hand_connections = mp.solutions.hands.HAND_CONNECTIONS
        except AttributeError:
            cam.release()
            self.error.emit(
                f"Video mode needs an older mediapipe — you have {getattr(mp, '__version__', '?')}, "
                "but mediapipe 0.10.31+ removed the hand-tracking API this feature uses. Run:\n"
                "  pip uninstall mediapipe -y\n"
                "  pip install mediapipe==0.10.21"
            )
            return
        except Exception as e:  # noqa: BLE001
            cam.release()
            self.error.emit(f"Hand tracking couldn't start: {e}")
            return

        engine = GestureEngine(self._load_cfg())
        eye_finder = self._make_eye_finder(cv2, mp)
        frame_index = 0
        eye_pt = None
        bad_reads = 0
        last_cfg_time = 0.0
        shown_status = ""

        self._running = True
        self._last_preview_time = 0.0
        self.status.emit("Camera on — gestures ready")
        try:
            while self._running:
                now = time.time()
                if now - last_cfg_time >= self._CFG_REFRESH:
                    last_cfg_time = now
                    engine.set_cfg(self._load_cfg())
                if self._pause_request is not None:
                    engine.set_paused(self._pause_request)
                    self._pause_request = None
                    self.status.emit("Paused" if engine.paused else "Resumed")

                ok, frame = cam.read()
                if not ok:
                    bad_reads += 1
                    if bad_reads > 100:
                        self.error.emit("The webcam stopped sending pictures (unplugged or taken by another app).")
                        return
                    time.sleep(0.03)
                    continue
                bad_reads = 0

                frame = cv2.flip(frame, 1)   # mirror: moving your right hand moves it right on screen
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False      # lets mediapipe skip an internal copy
                try:
                    result = hands.process(rgb)
                except Exception as e:  # noqa: BLE001
                    self.error.emit(f"Hand tracking failed: {e}")
                    return

                frame_index += 1
                if eye_finder is not None and frame_index % 3 == 0:
                    try:
                        eye_pt = eye_finder(rgb)
                    except Exception:  # noqa: BLE001
                        eye_pt = None

                found = result.multi_hand_landmarks or []
                hand_pt = None
                clean_rgb = rgb
                if found:
                    tip = found[0].landmark[8]
                    hand_pt = (float(tip.x), float(tip.y))
                # Only build the (costly) preview picture when one is due.
                if now - self._last_preview_time >= self._PREVIEW_INTERVAL:
                    rgb = rgb.copy()             # writable again
                    clean_rgb = rgb.copy() if found else rgb
                    for hand_landmarks in found:
                        drawing_utils.draw_landmarks(rgb, hand_landmarks, hand_connections)

                points = [[(p.x, p.y) for p in h.landmark] for h in found]
                for event in engine.update(points, now):
                    self._perform(pyautogui, event["action"])
                    shown_status = event["label"]
                    self.status.emit(shown_status)

                state = ("paused" if engine.paused
                         else "off" if not engine.cfg["gestures_enabled"] else "on")
                self._maybe_emit_preview(rgb, now, clean_rgb, hand_pt, eye_pt, {
                    "state": state, "gesture": engine.gesture,
                    "last": shown_status, "hands": len(found)})
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Gesture control stopped unexpectedly: {e}")
        finally:
            try:
                hands.close()
            except Exception:  # noqa: BLE001
                pass
            cam.release()
            self.status.emit("Video mode stopped.")

    # -- actions -------------------------------------------------------------
    def _perform(self, pyautogui, action: str) -> None:
        try:
            if action == "zoom_in":
                self._zoom(pyautogui, 120)
            elif action == "zoom_out":
                self._zoom(pyautogui, -120)
            elif action == "tab_next":
                pyautogui.hotkey("ctrl", "tab")
            elif action == "tab_prev":
                pyautogui.hotkey("ctrl", "shift", "tab")
            elif action == "desktop_next":
                pyautogui.hotkey("win", "ctrl", "right")
            elif action == "desktop_prev":
                pyautogui.hotkey("win", "ctrl", "left")
            elif action in ("volume_up", "volume_down"):
                self._change_volume(pyautogui, +1 if action == "volume_up" else -1)
            elif action in ("app_1", "app_2", "app_3"):
                pyautogui.hotkey("win", action[-1])
            # "pause" / "resume" need no key press
        except Exception as e:  # noqa: BLE001
            self.status.emit(f"Couldn't send {action}: {e}")

    def _change_volume(self, pyautogui, direction: int) -> None:
        step = int(user_prefs.get("gesture_volume_step"))
        if self._volume is None:
            self._volume = self._open_volume()
        if self._volume:
            try:
                level = self._volume.GetMasterVolumeLevelScalar()
                level = min(1.0, max(0.0, level + direction * step / 100.0))
                self._volume.SetMasterVolumeLevelScalar(level, None)
                return
            except Exception:  # noqa: BLE001
                self._volume = False
        # fallback: the keyboard volume keys (each press is about 2%)
        for _ in range(max(1, round(step / 2))):
            pyautogui.press("volumeup" if direction > 0 else "volumedown")

    @staticmethod
    def _open_volume():
        """pycaw master-volume endpoint (created on this thread), or False."""
        try:
            import comtypes
            comtypes.CoInitialize()
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            device = AudioUtilities.GetSpeakers()
            endpoint = getattr(device, "EndpointVolume", None)
            if endpoint is not None:
                return endpoint
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(interface, POINTER(IAudioEndpointVolume))
        except Exception:  # noqa: BLE001
            return False

    def _maybe_emit_preview(self, rgb_frame, now: float, clean_frame=None, hand=None, eye=None, info=None) -> None:
        """Throttled conversion of the already-RGB (and landmark-annotated)
        frame to a QImage for the HUD's left-side video panel. Same
        reasoning as _StartupWorker's preview throttle: emitting every
        captured frame floods the GUI thread with repaints."""
        if (now - self._last_preview_time) < self._PREVIEW_INTERVAL:
            return
        self._last_preview_time = now
        h, w, ch = rgb_frame.shape
        qimage = QImage(rgb_frame.data, w, h, ch * w, QImage.Format_RGB888).copy()
        clean = qimage
        if clean_frame is not None and clean_frame is not rgb_frame:
            clean = QImage(clean_frame.data, w, h, ch * w, QImage.Format_RGB888).copy()
        self.frame_ready.emit({"qimage": qimage, "clean": clean, "hand": hand, "eye": eye, **(info or {})})

    @staticmethod
    def _make_eye_finder(cv2, mp):
        """Returns a function rgb_frame -> (x, y) of one eye (0..1 coords in the
        mirrored frame), or None if no face is found. Uses mediapipe's face
        detector when available, else OpenCV's built-in face cascade."""
        try:
            detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=0.5)

            def find(rgb):
                res = detector.process(rgb)
                if not res.detections:
                    return None
                kp = res.detections[0].location_data.relative_keypoints
                # keypoints 0/1 are the two eyes; follow the one on the right side of the picture
                eye = max(kp[0], kp[1], key=lambda k: k.x)
                return (float(eye.x), float(eye.y))
            return find
        except Exception:
            pass
        try:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            if cascade.empty():
                return None

            def find(rgb):
                gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(80, 80))
                if len(faces) == 0:
                    return None
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                fh, fw = gray.shape[:2]
                return ((x + 0.68 * w) / fw, (y + 0.40 * h) / fh)
            return find
        except Exception:
            return None

    @staticmethod
    def _zoom(pyautogui, amount: int) -> None:
        """Ctrl+scroll — the same shortcut a trackpad pinch sends, so it
        works across browsers, image viewers, editors, etc."""
        pyautogui.keyDown("ctrl")
        try:
            pyautogui.scroll(amount)
        finally:
            pyautogui.keyUp("ctrl")
