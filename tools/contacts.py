"""
tools/contacts.py
-------------------
A tiny address book so you can say "email Mom" instead of typing the
address. Saved in data/contacts.json (name -> email). send_email looks
names up here, and every address you successfully send to is remembered
under its own address too, so "recent contacts" just works.
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


def resolve(to: str) -> str:
    """Returns an email address for `to`: unchanged if it already looks
    like one, else the saved contact with that name (case-insensitive),
    else the original text."""
    text = (to or "").strip()
    if _EMAIL.match(text):
        return text
    wanted = text.lower()
    for name, address in _load().items():
        if name.lower() == wanted:
            return address
    return text


def remember_recipient(address: str) -> None:
    data = _load()
    if address not in data.values():
        data[address] = address
        try:
            _save(data)
        except OSError:
            pass


def save_contact(name: str, email: str) -> dict:
    name, email = (name or "").strip(), (email or "").strip()
    if not name:
        return {"error": "A contact needs a name."}
    if not _EMAIL.match(email):
        return {"error": f"'{email}' doesn't look like a valid email address."}
    data = _load()
    data[name] = email
    try:
        _save(data)
    except OSError as e:
        return {"error": f"Couldn't save the contact: {e}"}
    return {"status": "saved", "name": name, "email": email}


def list_contacts() -> dict:
    data = _load()
    named = {k: v for k, v in data.items() if k != v}
    recent = sorted(v for k, v in data.items() if k == v)
    return {"contacts": named, "recent_addresses": recent}
