"""
tools/input_control.py
--------------------------
Stage 9: type arbitrary text into whatever window/field currently has
keyboard focus, and press individual keys/shortcuts — "type whatever I
say" dictation, system-wide, not limited to EV AI's own window. Uses
pyautogui, which simulates real keystrokes the same way a human
pressing keys would.

No confirmation gate: this is the direct voice-to-keyboard equivalent
of the user typing it themselves (same trust level as open_application
or open_website), not a separate destructive action EV AI decides to
take on its own. The usual caution still applies in practice: it types
into whatever currently has focus, so a misheard voice command can land
in the wrong place — same risk as a human typing in the wrong window.

pyautogui.typewrite() only handles plain ASCII reliably; non-ASCII text
(emoji, most non-English scripts) may not type correctly. If that turns
out to matter, the `keyboard` package handles Unicode better but needs
elevated privileges for its global hooks on some systems — worth
switching to only if ASCII turns out to be a real limitation in practice.
"""

import time


def type_text(text: str, interval: float = 0.02) -> dict:
    """Type `text` into whatever currently has keyboard focus."""
    try:
        import pyautogui
    except ImportError:
        return {"error": "pyautogui isn't installed. Run: pip install -r requirements.txt"}

    try:
        # A short pause gives whatever window should receive this a beat
        # to actually have focus before keystrokes start landing.
        time.sleep(0.3)
        pyautogui.typewrite(text, interval=interval)
    except Exception as e:
        return {"error": f"Could not type text: {e}"}
    return {"status": "typed", "length": len(text)}


def press_key(key: str) -> dict:
    """Press a single key or combo, e.g. 'enter', 'tab', 'ctrl+a', 'esc'."""
    try:
        import pyautogui
    except ImportError:
        return {"error": "pyautogui isn't installed. Run: pip install -r requirements.txt"}

    try:
        keys = [k.strip() for k in key.lower().split("+") if k.strip()]
        if not keys:
            return {"error": "No key given."}
        if len(keys) > 1:
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(keys[0])
    except Exception as e:
        return {"error": f"Could not press key(s) '{key}': {e}"}
    return {"status": "pressed", "key": key}
