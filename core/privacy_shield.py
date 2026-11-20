"""
core/privacy_shield.py
------------------------
Emergency lock and a one-press privacy shield. The shield mutes the computer's microphone and tells EV to stop using the
mic, camera and screen. It cannot switch off the webcam hardware itself: use the camera's own cover or Windows
Settings -> Privacy for that.
"""
from __future__ import annotations

import sys


def lock_windows() -> dict:
    """Lock this Windows session right now (the same as Win+L)."""
    if sys.platform != "win32":
        return {"error": "Locking is only implemented for Windows."}
    try:
        import ctypes
        if not ctypes.windll.user32.LockWorkStation():
            return {"error": "Windows refused to lock the screen."}
        return {"status": "locked"}
    except Exception as e:
        return {"error": f"Could not lock: {e}"}


def set_mic_muted(muted: bool) -> dict:
    """Mute or unmute the default microphone for the whole computer (needs the pycaw package)."""
    if sys.platform != "win32":
        return {"error": "Only implemented for Windows."}
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetMicrophone()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMute(1 if muted else 0, None)
        return {"status": "muted" if muted else "unmuted"}
    except Exception as e:
        return {"error": f"Could not change the microphone: {e}"}
