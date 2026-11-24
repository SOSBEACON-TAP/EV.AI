"""Checks for SAVED CONTACTS and CALL PHONE (no network, no Qt)."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import devices                      # noqa: E402
from tools import contacts, phone_call        # noqa: E402

fails = 0


def check(name, cond):
    global fails
    print(("ok   " if cond else "FAIL ") + name)
    fails += 0 if cond else 1


tmp = Path(tempfile.mkdtemp()) / "contacts.json"
contacts._PATH = tmp
tmp.write_text(json.dumps({"Mom": "mom@example.com", "dad@example.com": "dad@example.com"}), encoding="utf-8")

check("old name->email file still resolves", contacts.resolve("mom") == "mom@example.com")
check("recent address is not listed as a contact", [c["name"] for c in contacts.all_contacts()] == ["Mom"])
r = contacts.save_contact("Mom", phone="+91 98765 43210")
check("adding a phone keeps the email", r.get("phone") == "+919876543210" and contacts.resolve("Mom") == "mom@example.com")
check("phone_for by name (any case)", contacts.phone_for("mom") == "+919876543210")
check("phone_for a typed number", contacts.phone_for("98765 43210") == "9876543210")
check("partial name matches one contact", contacts.phone_for("mo") == "+919876543210")
check("bad email refused", "error" in contacts.set_contact("X", email="nope"))
check("bad phone refused", "error" in contacts.set_contact("X", phone="12"))
check("needs email or phone", "error" in contacts.set_contact("X"))
contacts.set_contact("Sam", phone="+14155550100")
contacts.set_contact("Samuel", phone="+14155550111", old_name="Sam")
check("rename moves the contact", [c["name"] for c in contacts.all_contacts()] == ["Mom", "Samuel"])
check("ambiguous partial name is not guessed", contacts.phone_for("Sa") == "+14155550111")   # only Samuel starts with Sa
check("delete works", contacts.delete_contact("Samuel") and not contacts.phone_for("Samuel"))
check("list_contacts has phone", contacts.list_contacts()["contacts"]["Mom"]["phone"] == "+919876543210")

sent = []
devices.ring_phone = lambda msg, *a, **k: (sent.append(msg) or (True, "ok"))
devices.connected_id = lambda: ""
r = phone_call.call_phone("Mom", confirmed=True)
check("no phone connected -> clear error", "error" in r and "connected" in r["error"].lower())
devices.connected_id = lambda: "ABCDEFGHIJ"
r = phone_call.call_phone("Mom", confirmed=True)
check("call is sent to the phone as CALL:number|name", r.get("status") == "calling" and sent[-1] == "CALL:+919876543210|Mom")
r = phone_call.call_phone("+44 20 7946 0958", confirmed=True)
check("a typed number works", sent[-1].startswith("CALL:+442079460958|"))
check("unknown name -> error", "error" in phone_call.call_phone("Nobody", confirmed=True))

sys.exit(1 if fails else 0)
