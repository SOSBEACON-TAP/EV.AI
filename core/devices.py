"""
core/devices.py
---------------
Connected device: pair EV with your phone using a device code. If you give EV
a task and the computer is switched off before it finishes, EV rings your
phone IN THE APP over the internet -- like a WhatsApp call, no SIM balance
and no phone number needed.

How it works
    * Each phone has its own random device code, e.g.  EV-4K9QZ-7TW2M-X
      (a secret id plus a check character so typos are caught).
    * Entering the code in Settings -> Connected device pairs this computer
      with that phone.
    * The alert is delivered through ntfy (free push service, ntfy.sh): the
      computer posts an "urgent" message to a private channel named after the
      code, and the phone -- subscribed to the same channel -- rings.
      Until the EV phone app exists, install the free "ntfy" app and
      subscribe to the channel shown in Settings.
    Keep the code private: anyone who knows it can send alerts to the channel.
"""

from __future__ import annotations

import secrets
import urllib.error
import urllib.request

from core import user_prefs

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_BODY_LEN = 10
DEFAULT_SERVER = "https://ntfy.sh"


def _check_char(body: str) -> str:
    total = sum((i + 1) * _ALPHABET.index(c) for i, c in enumerate(body))
    return _ALPHABET[total % 36]


def new_code() -> str:
    """A fresh random device code (the phone app makes one per phone)."""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_BODY_LEN))
    return f"EV-{body[:5]}-{body[5:]}-{_check_char(body)}"


def decode_code(code: str) -> str | None:
    """The secret id (10 characters) for a valid code, else None."""
    c = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    if len(c) == _BODY_LEN + 3 and c.startswith("EV"):
        c = c[2:]
    if len(c) != _BODY_LEN + 1 or any(ch not in _ALPHABET for ch in c):
        return None
    body, check = c[:-1], c[-1]
    return body if _check_char(body) == check else None


def topic_for(device_id: str) -> str:
    return "ev-" + device_id.lower()


def mask(device_id: str) -> str:
    return "EV-•••••-•••" + device_id[-2:]


# -- connection state ------------------------------------------------------------
def connected_id() -> str:
    return user_prefs.get("device_id") or ""


def connect(code: str) -> tuple[bool, str]:
    device_id = decode_code(code)
    if device_id is None:
        return False, "That code isn't valid. Check it and try again."
    user_prefs.set_value("device_id", device_id)
    return True, f"Connected to device {mask(device_id)}."


def disconnect() -> None:
    user_prefs.set_value("device_id", "")


# -- ringing the phone -------------------------------------------------------------
def server() -> str:
    return (user_prefs.get("device_server") or DEFAULT_SERVER).rstrip("/")


def _ascii(text: str) -> str:
    return text.encode("ascii", "ignore").decode()


def ring_phone(message: str, device_id: str | None = None, timeout: float = 6.0) -> tuple[bool, str]:
    """Send an urgent 'EV is calling' alert to the connected phone."""
    device_id = device_id or connected_id()
    if not device_id:
        return False, "No device is connected."
    req = urllib.request.Request(
        f"{server()}/{topic_for(device_id)}", data=message.encode("utf-8"), method="POST")
    req.add_header("Title", "EV is calling")
    req.add_header("Priority", "urgent")
    req.add_header("Tags", "telephone_receiver,rotating_light")
    req.add_header("Content-Type", "text/plain; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (200 <= resp.status < 300), "Ringing your phone."
    except urllib.error.HTTPError as e:
        return False, f"The alert service said {e.code}."
    except Exception as e:
        return False, f"Couldn't reach the alert service: {e}"


def shutdown_message(task: str) -> str:
    task = " ".join((task or "").split())[:90]
    if task:
        return (f"Your computer was switched off while EV was still working on: {task}. "
                "Turn it back on so EV can finish.")
    return "Your computer was switched off while EV was still working on a task."


def call_for_shutdown(task: str) -> tuple[bool, str]:
    """Called when the computer is going down with a task still running."""
    if not user_prefs.get("call_on_shutdown") or not connected_id():
        return False, "Phone call on shutdown is off or no device is connected."
    return ring_phone(shutdown_message(task))
