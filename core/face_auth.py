"""
core/face_auth.py
------------------
Stage 10: verifies the person opening EV AI is the enrolled owner via
the webcam before the app finishes starting.

Uses OpenCV's bundled Haar cascade (face detection) + its LBPH
recognizer (opencv-contrib-python), entirely offline — nothing is
uploaded anywhere, and there's no heavy dlib/CMake build to fight with
on Windows like the `face_recognition` package would need.

This is a casual "is this probably you" gate against someone else idly
opening the app on your PC, not a secure biometric lock — don't rely on
it the way you'd rely on Windows Hello or your account password.

Usage:
    enroll_owner()          # one-time setup, run from scripts/enroll_face.py
    verify_owner()          # -> (bool, reason) — called from the startup screen
    set_password()          # one-time setup, run from scripts/set_password.py
    verify_password()       # -> bool — the startup screen's fallback when the
                             #    face scan fails or the camera isn't usable
"""

import hashlib
import hmac
import json
import os
import time

from config import settings, APP_ROOT

_LABEL_FILE_NAME = "labels.json"
_MODEL_FILE_NAME = "lbph_model.yml"
_PASSWORD_FILE_NAME = "password.hash"
_OWNER_LABEL = 1  # LBPH needs an integer label; there's only ever one enrolled person
_PBKDF2_ITERATIONS = 200_000

# Bundled with the project (data/models/) rather than read from OpenCV's own
# cv2.data.haarcascades folder — recent opencv-python/opencv-contrib-python
# wheels (5.x) stopped shipping the data/*.xml cascade files inside the pip
# package at all, which leaves cv2.data.haarcascades pointing at an empty
# folder and detectMultiScale() failing with "(-215:Assertion failed)
# !empty()". Keeping our own copy sidesteps that regardless of which
# opencv-* version ends up installed.
_CASCADE_PATH = APP_ROOT / "data" / "models" / "haarcascade_frontalface_default.xml"


_REINSTALL_HINT = (
    "pip uninstall opencv-python opencv-python-headless opencv-contrib-python -y && "
    "pip install opencv-contrib-python"
)


def _cv2():
    """Lazily imports OpenCV, with a friendly error for the two ways this
    reliably breaks: the package isn't installed at all, or more than one
    opencv-* variant is installed in the same environment (opencv-python,
    opencv-contrib-python, opencv-python-headless all ship a top-level
    `cv2` package and silently overwrite each other's files — whichever
    installed last 'wins', and the result is often missing pieces from
    both, like cv2.face or even cv2.CascadeClassifier). The fix for
    either case is the same: uninstall all of them, then install only
    opencv-contrib-python."""
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError(f"Face check needs opencv-contrib-python. Run: {_REINSTALL_HINT}") from e
    if not hasattr(cv2, "face") or not hasattr(cv2, "CascadeClassifier"):
        raise RuntimeError(
            "Your opencv install looks incomplete or mixed with another opencv-* package "
            f"(opencv-python and opencv-contrib-python can't coexist cleanly). Run: {_REINSTALL_HINT}"
        )
    return cv2


def _paths():
    model_dir = settings.face_model_path
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir / _MODEL_FILE_NAME, model_dir / _LABEL_FILE_NAME


def _password_path():
    model_dir = settings.face_model_path
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir / _PASSWORD_FILE_NAME


def is_enrolled() -> bool:
    model_path, label_path = _paths()
    return model_path.exists() and label_path.exists()


def has_password_set() -> bool:
    return _password_path().exists()


def set_password(password: str) -> dict:
    """One-time (or re-run-to-change) setup for the password fallback
    the startup screen offers when the face scan fails or the webcam
    isn't usable. Stored as salt+PBKDF2-SHA256 hash, never the password
    itself — same "local only, never uploaded" spirit as the face model.
    Meant to be run from scripts/set_password.py; never called by the AI."""
    password = (password or "").strip()
    if len(password) < 4:
        return {"error": "Password needs to be at least 4 characters."}
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    _password_path().write_text(f"{salt.hex()}:{digest.hex()}", encoding="utf-8")
    return {"status": "password set"}


def verify_password(password: str) -> bool:
    """Constant-time check against the stored hash. Returns False (never
    raises) if no password has been set yet, or the stored file is
    unreadable/corrupt — the startup screen treats that the same as
    "wrong password" rather than crashing."""
    path = _password_path()
    if not path.exists():
        return False
    try:
        salt_hex, digest_hex = path.read_text(encoding="utf-8").strip().split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, OSError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(actual, expected)


def _detector(cv2):
    """Builds the face detector from the cascade file bundled with the
    project, falling back to OpenCV's own bundled copy if present (older
    opencv-* versions that still ship it). Raises RuntimeError with a
    clear message if neither is usable, rather than letting OpenCV's own
    cryptic "(-215:Assertion failed) !empty()" surface to the user."""
    if _CASCADE_PATH.exists():
        path = str(_CASCADE_PATH)
    else:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

    classifier = cv2.CascadeClassifier(path)
    if classifier.empty():
        raise RuntimeError(
            f"Could not load the face-detection file — expected it at {_CASCADE_PATH}. "
            "Make sure data/models/haarcascade_frontalface_default.xml was copied into the project."
        )
    return classifier


def enroll_owner(name: str = "owner", num_samples: int = 25, progress_callback=None) -> dict:
    """Capture `num_samples` face photos from the webcam and train the
    recognizer on them. Meant to be run once, interactively, from
    scripts/enroll_face.py — not called by the AI itself, since it needs
    the user actually looking at the camera, not just confirming a tool
    call.

    progress_callback(current, total), if given, is called after each
    captured sample (so a caller can drive a progress bar or a
    print-based one like scripts/enroll_face.py does). Returns a result
    dict with an "error" key on failure, same as the other tools in this
    project — it never raises."""
    try:
        cv2 = _cv2()
        detector = _detector(cv2)
    except RuntimeError as e:
        return {"error": str(e)}
    import numpy as np

    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cam.isOpened():
        return {"error": "Could not open the webcam (index 0). Is another app using it?"}

    samples = []
    try:
        attempts = 0
        max_attempts = num_samples * 15
        while len(samples) < num_samples and attempts < max_attempts:
            attempts += 1
            ok, frame = cam.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(120, 120))
            if len(faces) != 1:
                continue  # skip frames with no face, or more than one (someone else in shot)
            x, y, w, h = faces[0]
            samples.append(gray[y:y + h, x:x + w])
            if progress_callback:
                progress_callback(len(samples), num_samples)
            time.sleep(0.15)  # small gap so consecutive samples aren't near-identical
    finally:
        cam.release()

    if len(samples) < max(5, num_samples // 2):
        return {
            "error": f"Only captured {len(samples)} usable face photos — try again with "
                     "better lighting and facing the camera directly."
        }

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(samples, np.array([_OWNER_LABEL] * len(samples)))

    model_path, label_path = _paths()
    recognizer.write(str(model_path))
    label_path.write_text(json.dumps({str(_OWNER_LABEL): name}), encoding="utf-8")

    return {"status": "enrolled", "name": name, "samples": len(samples)}


def verify_owner(timeout_seconds: float | None = None, frame_callback=None) -> tuple[bool, str]:
    """Looks at the webcam for up to `timeout_seconds` (defaults to
    settings.FACE_AUTH_TIMEOUT) and returns (True, "") the moment it
    confidently recognizes the enrolled owner, or (False, reason)
    otherwise.

    If given, frame_callback(frame_bgr, face_rect, matched) is called
    once per captured frame — frame_rect is (x, y, w, h) of the largest
    detected face, or None if no face is in frame; matched is True only
    on the frame that confirms the owner. Meant for a caller (e.g. the
    startup screen) to show a live preview; a callback that raises is
    swallowed so a UI bug can never break the actual check.

    Nobody being enrolled yet, or OpenCV/the webcam not being available,
    both return (True, reason) rather than locking the user out of their
    own app — the lockout only ever happens once enrollment has actually
    succeeded and a face was looked for and not matched."""
    if not is_enrolled():
        return True, "No face enrolled yet — run scripts/enroll_face.py, then set FACE_AUTH_ENABLED=true."

    try:
        cv2 = _cv2()
        detector = _detector(cv2)
    except RuntimeError as e:
        return True, f"{e} (skipped the face check so you're not locked out)"

    model_path, label_path = _paths()
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(str(model_path))
    labels = json.loads(label_path.read_text(encoding="utf-8"))
    owner_name = labels.get(str(_OWNER_LABEL), "owner")

    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cam.isOpened():
        return False, "Could not open the webcam to check who you are."

    deadline = time.time() + (timeout_seconds if timeout_seconds is not None else settings.FACE_AUTH_TIMEOUT)
    try:
        while time.time() < deadline:
            ok, frame = cam.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(120, 120))

            face_rect = None
            matched = False
            if len(faces) > 0:
                # Only the largest face matters — this is a single-owner
                # gate, not a crowd scanner.
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                face_rect = (int(x), int(y), int(w), int(h))
                label, confidence = recognizer.predict(gray[y:y + h, x:x + w])
                # LBPH's "confidence" is really a distance — lower means a
                # closer match, the opposite of a normal confidence score.
                matched = label == _OWNER_LABEL and confidence <= settings.FACE_CONFIDENCE_THRESHOLD

            if frame_callback:
                try:
                    frame_callback(frame, face_rect, matched)
                except Exception:
                    pass

            if matched:
                return True, f"Recognized {owner_name}."
        return False, "Face not recognized."
    finally:
        cam.release()
