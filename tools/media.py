"""
tools/media.py
-----------------
Media playback control via simulated media keys — works the same way a
hardware media key on a keyboard would, so it controls whatever's
currently playing (Spotify, a browser tab, etc.) without needing to know
which app that is.
"""

import sys

if sys.platform == "win32":
    import ctypes

    _VK_MEDIA_PLAY_PAUSE = 0xB3
    _VK_MEDIA_NEXT_TRACK = 0xB0
    _VK_MEDIA_PREV_TRACK = 0xB1
    _VK_VOLUME_UP = 0xAF
    _VK_VOLUME_DOWN = 0xAE
    _VK_VOLUME_MUTE = 0xAD

    def _press_media_key(vk_code: int) -> None:
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # KEYEVENTF_KEYUP


def _require_windows() -> dict | None:
    if sys.platform != "win32":
        return {"error": "Media control is only implemented for Windows right now."}
    return None


def play_pause() -> dict:
    if (err := _require_windows()) is not None:
        return err
    _press_media_key(_VK_MEDIA_PLAY_PAUSE)
    return {"status": "ok", "action": "play_pause"}


def next_track() -> dict:
    if (err := _require_windows()) is not None:
        return err
    _press_media_key(_VK_MEDIA_NEXT_TRACK)
    return {"status": "ok", "action": "next_track"}


def previous_track() -> dict:
    if (err := _require_windows()) is not None:
        return err
    _press_media_key(_VK_MEDIA_PREV_TRACK)
    return {"status": "ok", "action": "previous_track"}


def volume_up() -> dict:
    if (err := _require_windows()) is not None:
        return err
    _press_media_key(_VK_VOLUME_UP)
    return {"status": "ok", "action": "volume_up"}


def volume_down() -> dict:
    if (err := _require_windows()) is not None:
        return err
    _press_media_key(_VK_VOLUME_DOWN)
    return {"status": "ok", "action": "volume_down"}


def mute() -> dict:
    if (err := _require_windows()) is not None:
        return err
    _press_media_key(_VK_VOLUME_MUTE)
    return {"status": "ok", "action": "mute"}
