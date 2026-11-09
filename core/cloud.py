"""
core/cloud.py
-------------
Optional EV AI account: sign in with an email and password on any device and your settings, remembered facts,
chat summary and game profiles come back. Built on Supabase (free), over plain HTTPS.

Privacy, in plain words:
  * Everything is ENCRYPTED ON THIS PC (AES-256-GCM, key made from your email + password) before it is uploaded.
    The server only ever stores unreadable text, so even the database owner cannot read your chats.
  * Because of that, if you FORGET your password the old data cannot be recovered (a reset gives an empty account).
  * API keys, tokens, PINs, Karen rules, locations and device codes are never uploaded.
  * Nothing is uploaded unless you sign in. Sign out stops syncing.

Server side (one time, in the Supabase SQL editor): see CLOUD_SETUP_SQL below.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SUPABASE_URL = "https://nsgoicmtsiwzftpdfjmw.supabase.co"
# A "publishable" key is designed to be public: the database rules (row level security) decide who sees what.
SUPABASE_KEY = "sb_publishable_Prf04f6xymKfs-Uwd6mRXA_HcePpjIP"

CLOUD_SETUP_SQL = """
create table if not exists public.user_data (
  user_id uuid primary key references auth.users(id) on delete cascade,
  data text not null,
  updated_at timestamptz not null default now()
);
alter table public.user_data enable row level security;
create policy "own row select" on public.user_data for select using (auth.uid() = user_id);
create policy "own row insert" on public.user_data for insert with check (auth.uid() = user_id);
create policy "own row update" on public.user_data for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own row delete" on public.user_data for delete using (auth.uid() = user_id);
"""

# Only these settings travel between devices (looks, voice, behaviour). Nothing secret, nothing device-specific.
SYNC_PREFS = (
    "theme", "speak_replies", "always_on_top", "minimize_to_tray", "global_hotkey", "briefing_on_start", "offline_first",
    "hover_sound", "profile", "auto_check_updates", "observe_interval_s", "personality", "voice_per_personality",
    "voice_professional", "voice_friendly", "voice_humorous", "ask_save_conversation", "battery_alerts", "long_term_memory",
    "font_scale", "window_opacity", "custom_accent1", "custom_accent2", "custom_bg", "presets_json", "home_hidden",
    "home_sizes", "focus_blocked", "focus_action", "confirm_before_sending", "usb_alert",
)
MAX_BLOB = 600_000          # characters of JSON before encryption


def _root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def _session_file() -> Path:
    return _root() / "data" / "cloud_session.json"


# ============================================================ encryption
def derive_key(email: str, password: str) -> bytes:
    """32-byte key from email + password. The salt is the email, so every device derives the same key."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), ("evai-sync:" + email.strip().lower()).encode(), 200_000, 32)


def encrypt(key: bytes, obj: dict) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    if len(raw) > MAX_BLOB:
        raise ValueError("too large")
    nonce = os.urandom(12)
    return "v1:" + base64.b64encode(nonce + AESGCM(key).encrypt(nonce, raw, None)).decode()


def decrypt(key: bytes, blob: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith("v1:"):
        raise ValueError("unknown format")
    raw = base64.b64decode(blob[3:])
    return json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], None).decode())


# ============================================================ what travels
def merge_lines(remote: list[str], local: list[str], cap: int = 60) -> list[str]:
    """Union of two chat-summary line lists: remote order first, then new local lines, newest kept."""
    out = list(remote)
    seen = set(out)
    for line in local:
        if line not in seen:
            out.append(line); seen.add(line)
    return out[-cap:]


def merge_memories(remote: list[dict], local: list[dict]) -> list[dict]:
    """Facts are matched by (category, key); the newer one wins."""
    by = {}
    for m in list(remote) + list(local):
        k = (m.get("category", "fact"), m.get("key", ""))
        if k not in by or str(m.get("created_at", "")) >= str(by[k].get("created_at", "")):
            by[k] = m
    return list(by.values())


def collect() -> dict:
    """Everything that may be uploaded, gathered from this PC."""
    from core import convo_memory, user_prefs
    prefs = user_prefs.load()
    snap = {"prefs": {k: prefs[k] for k in SYNC_PREFS if k in prefs}, "summary": convo_memory._load(),
            "memories": [], "profiles": {}}
    try:
        from core.memory import MemoryStore
        snap["memories"] = MemoryStore().recall()["memories"][:300]
    except Exception:
        pass
    try:
        from core import gamestats
        snap["profiles"] = gamestats.profiles()
    except Exception:
        pass
    return snap


def apply(remote: dict) -> dict:
    """Merges a downloaded snapshot into this PC and returns the merged snapshot (to upload back)."""
    from core import convo_memory, user_prefs
    local = collect()
    for k, v in (remote.get("prefs") or {}).items():
        if k in SYNC_PREFS and k in user_prefs.DEFAULTS and isinstance(v, type(user_prefs.DEFAULTS[k])):
            user_prefs.set_value(k, v)
    lines = merge_lines(list(remote.get("summary") or []), local["summary"])
    convo_memory._save(lines)
    mems = merge_memories(list(remote.get("memories") or []), local["memories"])
    try:
        from core.memory import MemoryStore
        store = MemoryStore()
        for m in mems:
            if m.get("key") and m.get("value"):
                store.remember(m.get("category", "fact"), m["key"], m["value"])
    except Exception:
        pass
    profiles = dict(remote.get("profiles") or {})
    profiles.update(local["profiles"])
    try:
        from core import gamestats
        for name, p in profiles.items():
            gamestats.save_profile(name, p.get("target", "Left mouse button"), p.get("cps", 10), p.get("break_on", True), p.get("break_min", 45))
    except Exception:
        pass
    return collect()


# ============================================================ talking to Supabase
def _real_http(method: str, url: str, headers: dict, body: dict | None, timeout: float = 15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode() or "null"
            return r.status, json.loads(txt)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


class Cloud:
    def __init__(self, http=None, session_path: Path | None = None):
        self._http = http or _real_http
        self._path = session_path or _session_file()
        self._s = self._load()          # {"email", "user_id", "refresh", "key"(b64)}
        self._access, self._expires = "", 0.0

    # ----------------------------------------------------- session
    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._s), encoding="utf-8")
        except OSError:
            pass

    @property
    def signed_in(self) -> bool:
        return bool(self._s.get("refresh") and self._s.get("key"))

    @property
    def email(self) -> str:
        return self._s.get("email", "")

    def _hdr(self, token: str | None = None) -> dict:
        h = {"apikey": SUPABASE_KEY}
        h["Authorization"] = "Bearer " + (token or SUPABASE_KEY)
        return h

    def _take_session(self, d: dict, email: str, key: bytes | None) -> None:
        self._access = d["access_token"]
        self._expires = time.time() + int(d.get("expires_in", 3600)) - 60
        self._s.update(email=email, user_id=(d.get("user") or {}).get("id", self._s.get("user_id", "")), refresh=d.get("refresh_token", ""))
        if key is not None:
            self._s["key"] = base64.b64encode(key).decode()
        self._save()

    @staticmethod
    def _err(code: int, d: dict) -> str:
        if code == 0:
            return "Couldn't reach the server. Check your internet."
        text = str(d.get("msg") or d.get("error_description") or d.get("message") or d.get("error") or "").lower()
        if "invalid login" in text or "invalid_credentials" in text:
            return "Wrong email or password (or the email isn't confirmed yet)."
        if "already" in text and "regist" in text:
            return "That email already has an account. Use Sign in."
        if "password" in text and ("least" in text or "weak" in text or "short" in text):
            return "Choose a longer password (at least 8 characters)."
        if "email" in text and "confirm" in text:
            return "Confirm your email first (check your inbox), then sign in."
        if code == 429:
            return "Too many tries. Wait a minute."
        return f"Server said no ({code}). {text[:80]}".strip()

    # ----------------------------------------------------- accounts
    def sign_up(self, email: str, password: str) -> tuple[bool, str]:
        email = email.strip().lower()
        if "@" not in email or len(password) < 8:
            return False, "Enter a valid email and a password of at least 8 characters."
        code, d = self._http("POST", SUPABASE_URL + "/auth/v1/signup", self._hdr(), {"email": email, "password": password})
        if code not in (200, 201):
            return False, self._err(code, d)
        if d.get("access_token"):
            self._take_session(d, email, derive_key(email, password))
            return True, "Account created and signed in."
        return True, "Account created. Check your email and confirm it, then press Sign in."

    def sign_in(self, email: str, password: str) -> tuple[bool, str]:
        email = email.strip().lower()
        if "@" not in email or not password:
            return False, "Enter your email and password."
        code, d = self._http("POST", SUPABASE_URL + "/auth/v1/token?grant_type=password", self._hdr(), {"email": email, "password": password})
        if code != 200 or not d.get("access_token"):
            return False, self._err(code, d)
        self._take_session(d, email, derive_key(email, password))
        return True, "Signed in."

    def sign_out(self) -> None:
        if self._access:
            self._http("POST", SUPABASE_URL + "/auth/v1/logout", self._hdr(self._access), {})
        self._s, self._access, self._expires = {}, "", 0.0
        try:
            self._path.unlink()
        except OSError:
            pass

    def _token(self) -> str | None:
        if self._access and time.time() < self._expires:
            return self._access
        if not self._s.get("refresh"):
            return None
        code, d = self._http("POST", SUPABASE_URL + "/auth/v1/token?grant_type=refresh_token", self._hdr(), {"refresh_token": self._s["refresh"]})
        if code != 200 or not d.get("access_token"):
            if code in (400, 401):                 # the session was revoked: ask for a password again
                self._s.pop("refresh", None); self._save()
            return None
        self._take_session(d, self._s.get("email", ""), None)
        return self._access

    # ----------------------------------------------------- data
    def pull(self) -> tuple[bool, dict | None, str]:
        tok = self._token()
        if not tok:
            return False, None, "Please sign in again."
        code, d = self._http("GET", SUPABASE_URL + "/rest/v1/user_data?select=data,updated_at&limit=1", self._hdr(tok), None)
        if code == 404 or (isinstance(d, dict) and "user_data" in str(d.get("message", "")) and "find" in str(d.get("message", ""))):
            return False, None, "The server isn't set up yet (the user_data table is missing)."
        if code != 200 or not isinstance(d, list):
            return False, None, self._err(code, d if isinstance(d, dict) else {})
        if not d:
            return True, None, "No saved data yet."
        try:
            return True, decrypt(base64.b64decode(self._s["key"]), d[0]["data"]), "ok"
        except Exception:
            return False, None, "Couldn't decrypt the saved data. Was it made with a different password?"

    def push(self, snapshot: dict) -> tuple[bool, str]:
        tok = self._token()
        if not tok:
            return False, "Please sign in again."
        try:
            blob = encrypt(base64.b64decode(self._s["key"]), snapshot)
        except ValueError:
            return False, "Your data is too large to sync."
        body = {"user_id": self._s.get("user_id"), "data": blob, "updated_at": datetime.now(timezone.utc).isoformat()}
        h = {**self._hdr(tok), "Prefer": "resolution=merge-duplicates,return=minimal"}
        code, d = self._http("POST", SUPABASE_URL + "/rest/v1/user_data?on_conflict=user_id", h, body)
        return (True, "Synced.") if code in (200, 201, 204) else (False, self._err(code, d if isinstance(d, dict) else {}))

    def sync(self) -> tuple[bool, str]:
        """Download, merge into this PC, upload the merged result."""
        ok, remote, msg = self.pull()
        if not ok:
            return False, msg
        merged = apply(remote) if remote else collect()
        ok, msg = self.push(merged)
        return ok, ("Synced: settings, facts and chat summary are up to date." if ok else msg)


_instance: "Cloud | None" = None


def get() -> Cloud:
    """The one shared account object (Settings and the main window use the same session)."""
    global _instance
    if _instance is None:
        _instance = Cloud()
    return _instance
