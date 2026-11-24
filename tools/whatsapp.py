"""
tools/whatsapp.py
--------------------
Stage 9: send a WhatsApp message via WhatsApp Web browser automation
(Playwright) — WhatsApp has no official API for this. Keeps one
persistent browser profile (config.settings.WHATSAPP_PROFILE_DIR) so
you only need to scan the WhatsApp QR code the first time ever; after
that the saved login session is reused automatically on every call.

This is slower and more fragile than send_email: it depends on
WhatsApp Web's page layout, which can change without notice. If a
selector below stops matching after a WhatsApp Web update, that's the
first thing to check and update.

The browser window is intentionally shown (headless=False), not
hidden — that's what makes the first-time QR-code scan possible, and
it also makes any failure far easier to diagnose than a headless black
box would be.
"""

from concurrent.futures import ThreadPoolExecutor

from config import settings
from core import user_prefs

_playwright = None
_browser_context = None
_page = None

# Playwright's sync API is bound to the thread that started it. EV AI's tools can
# be called from different worker threads, which breaks a reused page ("cannot
# switch to a different thread"), so every WhatsApp action runs on this one thread.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ev-whatsapp")

# WhatsApp Web changes its markup often, so each element has several selectors
# (comma = "any of these") instead of one brittle one.
_SEARCH_BOX = (
    'div[contenteditable="true"][data-tab="3"], '
    '[aria-label="Search input textbox"], '
    'div[role="textbox"][aria-label*="Search" i], '
    '#side div[contenteditable="true"]'
)
_MESSAGE_BOX = (
    'footer div[contenteditable="true"], '
    'div[contenteditable="true"][data-tab="10"], '
    'div[role="textbox"][aria-label*="message" i]'
)
_CHAT_LIST_ROW = '#pane-side span[title]'
_SEND_BUTTON = 'button[aria-label="Send"], span[data-icon="send"]'


def _ensure_session():
    """Lazily launches (once) a persistent Chromium context pointed at
    WhatsApp Web, reused across calls. Returns the Page, or raises
    RuntimeError with a message meant to be shown to the user."""
    global _playwright, _browser_context, _page

    if _page is not None and not _page.is_closed():
        return _page

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright isn't installed. Run: pip install -r requirements.txt, then run: "
            "python -m playwright install chromium"
        ) from e

    profile_dir = settings.whatsapp_profile_path
    profile_dir.mkdir(parents=True, exist_ok=True)

    if _playwright is None:
        _playwright = sync_playwright().start()

    _browser_context = _playwright.chromium.launch_persistent_context(
        str(profile_dir), headless=False, viewport={"width": 1100, "height": 800},
    )
    _page = _browser_context.pages[0] if _browser_context.pages else _browser_context.new_page()
    _page.goto("https://web.whatsapp.com", timeout=60_000)
    return _page


def _debug_shot(page, tag: str) -> str:
    """Save a screenshot so a failure can be diagnosed; returns a note for the error text."""
    try:
        path = settings.whatsapp_profile_path.parent / f"whatsapp_debug_{tag}.png"
        page.screenshot(path=str(path))
        return f" (screenshot saved: {path})"
    except Exception:
        return ""


def _pick_chat(page, contact: str):
    """Find the chat row for `contact`: exact name first, then a
    case-insensitive 'contains' match (so 'rakshan' finds 'Rakshan K')."""
    rows = page.locator(_CHAT_LIST_ROW)
    wanted = contact.strip().lower()
    deadline_ms = 6000
    waited = 0
    while waited < deadline_ms:
        count = rows.count()
        if count:
            titles = []
            for i in range(min(count, 15)):
                try:
                    titles.append((i, (rows.nth(i).get_attribute("title") or "").strip()))
                except Exception:
                    continue
            for i, t in titles:
                if t.lower() == wanted:
                    return rows.nth(i), t
            for i, t in titles:
                if wanted in t.lower():
                    return rows.nth(i), t
        page.wait_for_timeout(500)
        waited += 500
    return None, ""


def _send_blocking(contact: str, message: str) -> dict:
    try:
        page = _ensure_session()
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        # Covers Playwright's own exceptions (e.g. the browser failing to
        # launch) with a friendlier message than a raw stack trace.
        return {"error": f"Could not start the WhatsApp browser session: {e}"}

    try:
        search_box = page.locator(_SEARCH_BOX)
        if search_box.count() == 0:
            # QR-code screen (or still loading): give the user real time to scan.
            try:
                page.wait_for_selector(_SEARCH_BOX, timeout=180_000)
            except Exception:
                return {
                    "error": "The WhatsApp QR code wasn't scanned in time, so I gave up waiting. "
                             "Try again — as soon as the Chromium window shows the QR code, scan it "
                             "with your phone: WhatsApp → Settings (or ⋮) → Linked Devices → Link a Device."
                }
            page.wait_for_timeout(1500)  # let the chat list finish loading after login
            search_box = page.locator(_SEARCH_BOX)

        search_box.first.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(contact, delay=40)
        page.wait_for_timeout(1200)  # let the filtered chat list render

        row, found = _pick_chat(page, contact)
        if row is None:
            note = _debug_shot(page, "nochat")
            return {
                "error": f"Couldn't find a chat matching '{contact}' in WhatsApp — "
                         f"check the name as it appears in your chat list.{note}"
            }
        row.click()

        message_box = page.locator(_MESSAGE_BOX)
        message_box.first.wait_for(timeout=15_000)
        message_box.first.click()
        page.keyboard.insert_text(message)
        page.wait_for_timeout(300)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)

        # If the text is still sitting in the box, Enter didn't send: click Send.
        try:
            leftover = message_box.first.inner_text().strip()
        except Exception:
            leftover = ""
        if leftover:
            btn = page.locator(_SEND_BUTTON)
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(1000)
                try:
                    leftover = message_box.first.inner_text().strip()
                except Exception:
                    leftover = ""
        if leftover:
            note = _debug_shot(page, "notsent")
            return {"error": f"I typed the message but WhatsApp didn't send it.{note}"}
    except Exception as e:
        note = _debug_shot(page, "error")
        return {"error": f"WhatsApp automation failed: {e}{note}"}

    return {"status": "sent", "contact": found or contact}


def send_whatsapp_message(contact: str, message: str, confirmed: bool = False) -> dict:
    """Send a WhatsApp message to a contact by name (case-insensitive; a
    partial name is fine if it's unambiguous in your chat list)."""
    if not confirmed and user_prefs.get("confirm_before_sending"):
        return {
            "confirmation_required": True,
            "message": f"This will open WhatsApp Web and send a message to '{contact}'. Ask the user to confirm first.",
        }
    import sys
    if getattr(sys, "frozen", False):
        return _send_via_link(contact, message)      # the packaged app carries no browser for Playwright: use WhatsApp's own links
    try:
        import playwright  # noqa: F401
    except ImportError:
        return _send_via_link(contact, message)
    try:
        r = _executor.submit(_send_blocking, contact, message).result()
    except Exception as e:
        r = {"error": f"WhatsApp automation failed: {e}"}
    if isinstance(r, dict) and "error" in r and ("Executable doesn't exist" in r["error"] or "playwright install" in r["error"]
                                                  or "Could not start the WhatsApp browser session" in r["error"]):
        return _send_via_link(contact, message)      # no Playwright browser installed: do it the simple way instead
    return r


# ---- no-Playwright route: open WhatsApp (desktop app or the browser you are already logged in with) --------------
_NUMBERS_PATH = None


def _numbers_path():
    from config import APP_ROOT
    return APP_ROOT / "data" / "wa_numbers.json"


def _load_numbers() -> dict:
    import json
    try:
        d = json.loads(_numbers_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_wa_number(name: str, number: str) -> None:
    """Remember a WhatsApp number under a name so 'message Mom' works later."""
    import json
    name = (name or "").strip()
    num = _digits(number)
    if not name or not num:
        return
    d = _load_numbers()
    d[name] = num
    try:
        _numbers_path().parent.mkdir(parents=True, exist_ok=True)
        _numbers_path().write_text(json.dumps(d, indent=2), encoding="utf-8")
    except OSError:
        pass


def _digits(text: str) -> str:
    import re
    d = re.sub(r"\D", "", text or "")
    return d if 8 <= len(d) <= 15 else ""


def _to_number(contact: str) -> str:
    num = _digits(contact)
    if num:
        return num
    low = (contact or "").strip().lower()
    for name, n in _load_numbers().items():
        if name.lower() == low:
            return n
    try:                                              # SAVED CONTACTS (EV ACTIONS) keep a phone number per name too
        from tools import contacts
        return _digits(contacts.phone_for(contact))
    except Exception:
        return ""


def _send_via_link(contact: str, message: str) -> dict:
    """Open the chat with the message already typed, then press Enter once the window is in front.

    With the WhatsApp desktop app installed, its own whatsapp:// link is used. Without it (no app, or one we cannot find)
    EV goes straight to WhatsApp Web in the browser: handing Windows a whatsapp:// link with nothing to open it makes
    Windows ask the person to download an app, which is the thing we must not do."""
    import os
    import time
    import urllib.parse
    num = _to_number(contact)
    if not num:
        return {"error": f"I need a phone number for '{contact}'. Type it with the country code, for example +91 98765 43210, "
                         "or save the contact under SAVED CONTACTS, and I will remember it under that name."}
    text = urllib.parse.quote(message)
    use_app = False
    try:
        from core.winapps import whatsapp_desktop_installed
        use_app = whatsapp_desktop_installed()
    except Exception:
        use_app = False
    opened_app = False
    if use_app:
        try:
            os.startfile(f"whatsapp://send?phone={num}&text={text}")
            opened_app = True
        except Exception:
            opened_app = False
    if not opened_app:
        try:
            import webbrowser
            webbrowser.open(f"https://web.whatsapp.com/send?phone={num}&text={text}")
        except Exception as e:
            return {"error": f"Could not open WhatsApp Web: {e}"}
    # Press Enter once a WhatsApp window is in front. WhatsApp Web needs longer to load the chat than the app does, and
    # Enter on an empty message box does nothing, so a second try later is harmless. Never press it into another window.
    waits = (2.0,) if opened_app else (9.0, 5.0)
    sent = False
    try:
        from core.focus_match import active_window
        import pyautogui

        def whatsapp_in_front() -> bool:
            win = active_window()
            return bool(win and "whatsapp" in (win[1] or "").lower())

        for _ in range(40):                          # up to ~20 s for the WhatsApp window to appear in front
            time.sleep(0.5)
            if whatsapp_in_front():
                for pause in waits:
                    time.sleep(pause)                # let the chat load and the typed message appear
                    if not whatsapp_in_front():
                        break
                    pyautogui.press("enter")
                    sent = True
                break
    except Exception:
        pass
    if opened_app:
        if sent:
            return {"status": "sent", "contact": contact, "note": "Sent through WhatsApp's own window."}
        return {"status": "opened", "contact": contact,
                "note": "WhatsApp is open with your message typed. Press Enter to send it (I could not confirm the window was in front)."}
    note = ("WhatsApp is not installed on this PC, so I used WhatsApp Web in your browser. "
            + ("I pressed Enter once the chat opened; if the message is still in the box, press Enter. "
               if sent else "The message is typed in the chat. Press Enter to send it. ")
            + "The first time, WhatsApp Web shows a QR code: on your phone open WhatsApp, Linked devices, Link a device, and scan it.")
    return {"status": "opened", "contact": contact, "via": "WhatsApp Web", "note": note}


def _close_blocking() -> dict:
    global _browser_context, _page
    if _browser_context is not None:
        try:
            _browser_context.close()
        finally:
            _browser_context = None
            _page = None
        return {"status": "closed"}
    return {"status": "not_open"}


def close_whatsapp_session() -> dict:
    """Closes the WhatsApp Web browser session, if one is open. Doesn't
    log out — the saved profile still remembers the login next time."""
    try:
        return _executor.submit(_close_blocking).result()
    except Exception as e:
        return {"error": f"Could not close WhatsApp: {e}"}
