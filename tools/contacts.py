"""
tools/contacts.py
-------------------
A tiny address book so you can say "email Mom", "WhatsApp Mom" or "call Mom" instead of typing the
address or number. Saved in data/contacts.json.

Each saved contact has a name plus an email address and/or a phone number. Older files stored just
name -> email text; those still load (the text is read as the email). Every address you successfully
send to is also remembered under its own address ("recent addresses"), so recents just work.
"""

import json
import re

from config import APP_ROOT

_PATH = APP_ROOT / "data" / "contacts.json"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _load() -> dict:
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clean_phone(text: str) -> str:
    """'+91 98765-43210' -> '+919876543210'. Empty when it is not a plausible number (8 to 15 digits)."""
    text = (text or "").strip()
    digits = re.sub(r"\D", "", text)
    if not 8 <= len(digits) <= 15:
        return ""
    return ("+" if text.startswith("+") else "") + digits


def _entry(value) -> dict:
    """Any stored value -> {"email": ..., "phone": ...}."""
    if isinstance(value, dict):
        return {"email": str(value.get("email", "") or ""), "phone": str(value.get("phone", "") or "")}
    return {"email": str(value or ""), "phone": ""}


def _is_recent(name: str, value) -> bool:
    return isinstance(value, str) and name == value


def _find(data: dict, who: str):
    """The stored (name, entry) for `who`: exact name first (any case), then a unique 'contains' match."""
    wanted = (who or "").strip().lower()
    if not wanted:
        return None
    named = [(k, _entry(v)) for k, v in data.items() if not _is_recent(k, v)]
    for k, e in named:
        if k.lower() == wanted:
            return k, e
    part = [(k, e) for k, e in named if wanted in k.lower()]
    return part[0] if len(part) == 1 else None


def resolve(to: str) -> str:
    """Returns an email address for `to`: unchanged if it already looks like one, else the saved contact
    with that name (case-insensitive), else the original text."""
    text = (to or "").strip()
    if _EMAIL.match(text):
        return text
    found = _find(_load(), text)
    if found and found[1]["email"]:
        return found[1]["email"]
    return text


def phone_for(who: str) -> str:
    """A phone number for `who`: the text itself if it already is a number, else the saved contact's number, else ''."""
    direct = clean_phone(who)
    if direct:
        return direct
    found = _find(_load(), who)
    return found[1]["phone"] if found else ""


def display_name(who: str) -> str:
    """The saved name that `who` matches (so 'mom' shows as 'Mom'), or `who` unchanged."""
    found = _find(_load(), who)
    return found[0] if found else (who or "").strip()


def remember_recipient(address: str) -> None:
    data = _load()
    if address not in data.values() and address not in data:
        data[address] = address
        try:
            _save(data)
        except OSError:
            pass


def set_contact(name: str, email: str = "", phone: str = "", old_name: str = "") -> dict:
    """Create or replace a contact (both fields are overwritten, so an editor can clear one). `old_name` renames."""
    name, email = (name or "").strip(), (email or "").strip()
    if not name:
        return {"error": "A contact needs a name."}
    if not email and not (phone or "").strip():
        return {"error": "Give an email address, a phone number, or both."}
    if email and not _EMAIL.match(email):
        return {"error": f"'{email}' doesn't look like a valid email address."}
    num = ""
    if (phone or "").strip():
        num = clean_phone(phone)
        if not num:
            return {"error": f"'{phone}' doesn't look like a phone number. Use the country code, for example +91 98765 43210."}
    data = _load()
    if old_name and old_name != name:
        data.pop(old_name, None)
    data[name] = {"email": email, "phone": num}
    try:
        _save(data)
    except OSError as e:
        return {"error": f"Couldn't save the contact: {e}"}
    return {"status": "saved", "name": name, "email": email, "phone": num}


def save_contact(name: str, email: str = "", phone: str = "") -> dict:
    """The tool the AI uses: adds what it is given and keeps the other field of an existing contact."""
    old = _find(_load(), name)
    if old and (old[0].lower() == (name or "").strip().lower()):
        email = (email or "").strip() or old[1]["email"]
        phone = (phone or "").strip() or old[1]["phone"]
    return set_contact(name, email, phone)


def delete_contact(name: str) -> bool:
    data = _load()
    if name in data and not _is_recent(name, data[name]):
        del data[name]
        try:
            _save(data)
        except OSError:
            return False
        return True
    return False


def all_contacts() -> list[dict]:
    """[{"name", "email", "phone"}], sorted by name; recent addresses are not included."""
    out = []
    for k, v in _load().items():
        if _is_recent(k, v):
            continue
        e = _entry(v)
        out.append({"name": k, **e})
    return sorted(out, key=lambda c: c["name"].lower())


def list_contacts() -> dict:
    data = _load()
    named = {c["name"]: {k: v for k, v in c.items() if k != "name" and v} for c in all_contacts()}
    recent = sorted(v for k, v in data.items() if _is_recent(k, v))
    return {"contacts": named, "recent_addresses": recent}
