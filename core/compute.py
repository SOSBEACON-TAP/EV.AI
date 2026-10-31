"""
core/compute.py
---------------
"Compute": your phone/tablet controls this computer, but ONLY when both agree.

Agreement happens twice:
  1. Pairing. This computer shows a 6-digit PIN. You type it into the EV AI
     app on the phone and tap "Request control". This computer then asks
     "Allow <phone> to control this PC?". Only if you press Allow does it hand
     the phone a secret key.
  2. Every session. When the phone starts a session the computer asks again
     (unless you turned on "trust this phone"). While a session is on, a
     banner with a STOP button is shown, and the session ends by itself after
     SESSION_MINUTES.

Security design (v1)
    * Messages travel through the ntfy relay (same as the call alert), but are
      ENCRYPTED and authenticated with AES-256-GCM using the paired key, so the
      relay (or anyone who learns the topic) can read and forge nothing.
    * Each message carries a timestamp and a random nonce; old or repeated
      messages are rejected (replay protection).
    * Pairing messages are encrypted with a key derived from the PIN
      (PBKDF2), and the pairing channel closes after PAIR_MINUTES.
    * Commands outside the allow-list are refused. Nothing is run through a
      shell; mouse/keyboard use pyautogui only.
    * The key lives in data/compute.json (never committed to GitHub).

This module has no Qt code so it can be tested on its own. The UI hooks in
(ui/compute_ui.py) supply the consent dialogs and the banner.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

PAIR_MINUTES = 5
SESSION_MINUTES = 30
MAX_SKEW_SECONDS = 60
SERVER = "https://ntfy.sh"


# ----------------------------------------------------------------- crypto
def _aes():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM


def pin_key(pin: str, device_id: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), ("ev-compute-" + device_id).encode(), 100_000, 32)


def seal(key: bytes, obj: dict) -> bytes:
    """nonce(12) + AES-GCM(ciphertext+tag) of the JSON object."""
    nonce = os.urandom(12)
    return nonce + _aes()(key).encrypt(nonce, json.dumps(obj, separators=(",", ":")).encode(), b"ev-compute")


def unseal(key: bytes, data: bytes) -> dict | None:
    try:
        raw = _aes()(key).decrypt(data[:12], data[12:], b"ev-compute")
        obj = json.loads(raw.decode())
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def seal_bytes(key: bytes, raw: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + _aes()(key).encrypt(nonce, raw, b"ev-compute-bin")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(text: str) -> bytes:
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def session_topic(device_id: str, key: bytes) -> str:
    return f"evc-{device_id.lower()}-{hashlib.sha256(key).hexdigest()[:12]}"


def pair_topic(device_id: str, pin: str) -> str:
    return f"evp-{device_id.lower()}-{pin}"


# -------------------------------------------------------------- transport
class NtfyTransport:
    """post() sends bytes to a topic; stream() calls on_event(event_dict) for every message."""

    def __init__(self, server: str = SERVER):
        self.server = server.rstrip("/")

    def post_text(self, topic: str, text: str) -> None:
        req = urllib.request.Request(f"{self.server}/{topic}", data=text.encode(), method="POST")
        req.add_header("Cache", "no")
        urllib.request.urlopen(req, timeout=8).close()

    def post_file(self, topic: str, data: bytes, name: str) -> None:
        req = urllib.request.Request(f"{self.server}/{topic}", data=data, method="PUT")
        req.add_header("Filename", name)
        req.add_header("Cache", "no")
        urllib.request.urlopen(req, timeout=30).close()

    def fetch(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read()

    def stream(self, topic: str, on_event: Callable[[dict], None], stop: threading.Event) -> None:
        since = str(int(time.time()))
        while not stop.is_set():
            try:
                with urllib.request.urlopen(f"{self.server}/{topic}/json?since={since}", timeout=90) as resp:
                    for line in resp:
                        if stop.is_set():
                            return
                        try:
                            ev = json.loads(line.decode("utf-8", "ignore"))
                        except Exception:
                            continue
                        if ev.get("event") == "message":
                            since = ev.get("id", since)
                            on_event(ev)
            except Exception:
                if stop.wait(3):
                    return


# ------------------------------------------------------------------ store
def _store_path() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent.parent
    return root / "data" / "compute.json"


def load_store() -> dict:
    try:
        return json.loads(_store_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_store(data: dict) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------- actions
_VOLUME_KEYS = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD}


def _lock() -> str:
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return "Locked."


def _sleep() -> str:
    import subprocess
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    return "Going to sleep."


def _vk(name: str) -> str:
    import ctypes
    code = _VOLUME_KEYS[name]
    for _ in range(1 if name == "mute" else 3):
        ctypes.windll.user32.keybd_event(code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(code, 0, 2, 0)
    return "Done."


def _status() -> str:
    import psutil
    bat = psutil.sensors_battery()
    b = f", battery {int(bat.percent)}%" if bat else ""
    return f"CPU {psutil.cpu_percent(interval=0.3):.0f}%, RAM {psutil.virtual_memory().percent:.0f}%{b}"


def _screenshot(scale: float = 0.5, quality: int = 45) -> bytes:
    import io
    import pyautogui
    img = pyautogui.screenshot().convert("RGB")
    scale = min(1.0, max(0.2, float(scale)))
    img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=int(quality))
    return buf.getvalue()


def _pg():
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    return pyautogui


def _frac(v) -> float:
    return min(1.0, max(0.0, float(v)))


class ComputeHost:
    """Runs on the computer. All UI interaction goes through the callbacks."""

    def __init__(self, device_id: Callable[[], str],
                 ask_pair: Callable[[str], bool], ask_session: Callable[[str], bool],
                 on_state: Callable[[str, str], None] = lambda kind, text: None,
                 transport: NtfyTransport | None = None):
        self._device_id = device_id
        self.ask_pair = ask_pair
        self.ask_session = ask_session
        self.on_state = on_state     # kind in {"pairing","paired","session","ended","error"}
        self.tx = transport or NtfyTransport()
        self._stop = threading.Event()
        self._pair_stop = threading.Event()
        self._session_until = 0.0
        self._phone_name = ""
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    # -- state ----------------------------------------------------------
    @property
    def key(self) -> bytes | None:
        k = load_store().get("key")
        return bytes.fromhex(k) if k else None

    @property
    def session_active(self) -> bool:
        return time.time() < self._session_until

    def is_paired(self) -> bool:
        return self.key is not None

    def unpair(self) -> None:
        self.end_session("Unpaired.")
        save_store({})
        self.restart()

    # -- pairing --------------------------------------------------------
    def start_pairing(self) -> str:
        """Show the returned PIN to the user; the phone types it in."""
        dev = self._device_id()
        if not dev:
            raise RuntimeError("Connect your phone first (Settings, Connected device).")
        pin = f"{secrets.randbelow(10**6):06d}"
        self._pair_stop.set()
        self._pair_stop = threading.Event()
        stop = self._pair_stop
        pkey = pin_key(pin, dev)
        topic = pair_topic(dev, pin)
        deadline = time.time() + PAIR_MINUTES * 60

        def on_event(ev: dict) -> None:
            if time.time() > deadline:
                stop.set()
                return
            try:
                msg = unseal(pkey, unb64(ev.get("message", "")))
            except Exception:
                return
            if not msg or msg.get("k") != "req" or abs(time.time() - float(msg.get("t", 0))) > 120:
                return
            name = str(msg.get("name", "a phone"))[:40]
            if self.ask_pair(name):
                key = secrets.token_bytes(32)
                save_store({"key": key.hex(), "name": name})
                self.tx.post_text(topic, b64(seal(pkey, {"k": "grant", "key": key.hex(), "t": time.time()})))
                self.on_state("paired", name)
                self.restart()
            else:
                self.tx.post_text(topic, b64(seal(pkey, {"k": "deny", "t": time.time()})))
            stop.set()

        threading.Thread(target=self.tx.stream, args=(topic, on_event, stop), daemon=True).start()
        timer = threading.Timer(PAIR_MINUTES * 60, stop.set)
        timer.daemon = True
        timer.start()
        self.on_state("pairing", pin)
        return pin

    # -- session listener ----------------------------------------------
    def start(self) -> None:
        key, dev = self.key, self._device_id()
        if not key or not dev:
            return
        self._stop = threading.Event()
        topic = session_topic(dev, key)
        threading.Thread(target=self.tx.stream, args=(topic, self._on_event, self._stop), daemon=True).start()

    def restart(self) -> None:
        self._stop.set()
        self.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._pair_stop.set()
        self._session_until = 0.0

    def end_session(self, why: str = "Session ended.") -> None:
        was = self.session_active
        self._session_until = 0.0
        if was:
            self.on_state("ended", why)

    # -- messages --------------------------------------------------------
    def _send(self, obj: dict) -> None:
        key, dev = self.key, self._device_id()
        if key and dev:
            obj["d"] = "r"
            obj["t"] = time.time()
            try:
                self.tx.post_text(session_topic(dev, key), b64(seal(key, obj)))
            except Exception:
                pass

    def _on_event(self, ev: dict) -> None:
        key = self.key
        if not key or ev.get("attachment"):
            return
        try:
            msg = unseal(key, unb64(ev.get("message", "")))
        except Exception:
            return
        if not msg or msg.get("d") != "c":
            return
        now = time.time()
        if abs(now - float(msg.get("t", 0))) > MAX_SKEW_SECONDS:
            return
        n = str(msg.get("n", ""))
        with self._lock:
            self._seen = {k: v for k, v in self._seen.items() if now - v < 300}
            if not n or n in self._seen:
                return
            self._seen[n] = now
        try:
            reply = self.handle(msg)
        except Exception as e:
            reply = {"ok": False, "msg": f"Error: {e}"}
        reply["n"] = n
        self._send(reply)

    def handle(self, msg: dict) -> dict:
        cmd = str(msg.get("cmd", ""))
        a = msg.get("a") if isinstance(msg.get("a"), dict) else {}
        if cmd == "ping":
            return {"ok": True, "msg": "pong", "active": self.session_active}
        if cmd == "hello":
            name = str(a.get("name", "your phone"))[:40]
            if self.session_active:
                return {"ok": True, "msg": "Session already on."}
            if self.ask_session(name):
                self._session_until = time.time() + SESSION_MINUTES * 60
                self._phone_name = name
                self.on_state("session", name)
                return {"ok": True, "msg": "Session started.", "minutes": SESSION_MINUTES}
            return {"ok": False, "msg": "The computer said no."}
        if cmd == "bye":
            self.end_session("The phone ended the session.")
            return {"ok": True, "msg": "Ended."}
        if not self.session_active:
            return {"ok": False, "msg": "No active session. Start one and allow it on the computer."}
        return self._run(cmd, a)

    def _run(self, cmd: str, a: dict) -> dict:
        ok = lambda m="Done.": {"ok": True, "msg": m}  # noqa: E731
        if cmd == "status":
            return ok(_status())
        if cmd == "lock":
            return ok(_lock())
        if cmd == "sleep":
            return ok(_sleep())
        if cmd in _VOLUME_KEYS:
            return ok(_vk(cmd))
        if cmd == "open_app":
            from tools.applications import open_application
            r = open_application(str(a.get("name", ""))[:60])
            return {"ok": True, "msg": str(r)[:200]}
        if cmd == "screenshot":
            data = seal_bytes(self.key, _screenshot(a.get("scale", 0.5), a.get("q", 45)))
            dev = self._device_id()
            self.tx.post_file(session_topic(dev, self.key), data, f"shot-{secrets.token_hex(4)}.bin")
            return ok("Screenshot sent.")
        if cmd not in ("move", "click", "scroll", "type", "key"):
            return {"ok": False, "msg": "Unknown command."}
        pg = _pg()
        w, h = pg.size()
        if cmd == "move":
            pg.moveTo(int(_frac(a["x"]) * (w - 1)), int(_frac(a["y"]) * (h - 1)))
            return ok()
        if cmd == "click":
            if "x" in a:
                pg.moveTo(int(_frac(a["x"]) * (w - 1)), int(_frac(a["y"]) * (h - 1)))
            btn = a.get("button", "left")
            pg.click(button=btn if btn in ("left", "right", "middle") else "left", clicks=2 if a.get("double") else 1)
            return ok()
        if cmd == "scroll":
            pg.scroll(max(-20, min(20, int(a.get("dy", 0)))) * 40)
            return ok()
        if cmd == "type":
            pg.write(str(a.get("text", ""))[:300], interval=0.01)
            return ok()
        if cmd == "key":
            name = str(a.get("name", ""))
            if name in _ALLOWED_KEYS:
                pg.press(name)
                return ok()
            return {"ok": False, "msg": "That key isn't allowed."}
        return {"ok": False, "msg": "Unknown command."}


_ALLOWED_KEYS = {"enter", "esc", "tab", "backspace", "delete", "up", "down", "left", "right", "space",
                 "home", "end", "pageup", "pagedown", "playpause", "nexttrack", "prevtrack", "win"}
