"""
tools/phone_call.py
--------------------
CALL PHONE: start a phone call to a saved contact (or a number) from the computer. The call is made by YOUR phone:
EV sends the number to the connected EV phone app, which shows a call card, and you tap the green button there.
EV never dials by itself, so a stranger who learned the device code cannot make your phone call anyone.
"""

from core import devices, user_prefs
from tools import contacts


def call_phone(to: str, confirmed: bool = False) -> dict:
    """Call a saved contact by name, or a phone number (with country code), using the connected phone."""
    number = contacts.phone_for(to)
    if not number:
        return {"error": f"I don't have a phone number for '{to}'. Say the number with the country code, "
                         "or save the contact first (EV ACTIONS, SAVED CONTACTS)."}
    name = "" if contacts.clean_phone(to) else contacts.display_name(to)
    if not confirmed and user_prefs.get("confirm_before_sending"):
        return {"confirmation_required": True,
                "message": f"This will ask your phone to call {name or number}. Ask the user to confirm first."}
    ok, msg = devices.call_via_phone(number, name)
    return {"status": "calling", "contact": name or number, "note": msg} if ok else {"error": msg}
