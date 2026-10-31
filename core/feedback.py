"""
core/feedback.py
----------------
Send feedback from Settings to the developer's email through a free form
service, so no email password is ever stored in the app.

Set FEEDBACK_URL in app_version.py to ONE of:
    https://formspree.io/f/<your form id>              (Formspree)
    web3forms:<your access key>                        (Web3Forms, the key is public by design)
Both forward each submission to the email you registered with them.
"""

import json
import platform
import time
import urllib.request

_last_sent = 0.0


def configured() -> bool:
    try:
        from app_version import FEEDBACK_URL
        return bool(FEEDBACK_URL)
    except Exception:
        return False


def send(message: str, contact: str = "") -> tuple[bool, str]:
    global _last_sent
    from app_version import FEEDBACK_URL, VERSION
    message = (message or "").strip()
    if not FEEDBACK_URL:
        return False, "Feedback isn't set up in this build yet."
    if len(message) < 3:
        return False, "Please write your feedback first."
    if time.time() - _last_sent < 30:
        return False, "Please wait a few seconds before sending another message."
    body = {"message": message[:4000], "contact": contact.strip()[:120],
            "app": f"EV AI {VERSION}", "system": f"{platform.system()} {platform.release()}"}
    if FEEDBACK_URL.startswith("web3forms:"):
        url = "https://api.web3forms.com/submit"
        body.update(access_key=FEEDBACK_URL.split(":", 1)[1], subject="EV AI feedback",
                    from_name=contact.strip()[:60] or "EV AI user")
    else:
        url = FEEDBACK_URL
        if contact.strip():
            body["email"] = contact.strip()[:120]
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "User-Agent": "EV.AI"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if 200 <= r.status < 300:
                _last_sent = time.time()
                return True, "Thank you! Your feedback was sent."
            return False, f"The feedback service said {r.status}."
    except Exception as e:
        return False, f"Couldn't send feedback: {e}"
