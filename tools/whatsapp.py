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
    try:
        return _executor.submit(_send_blocking, contact, message).result()
    except Exception as e:
        return {"error": f"WhatsApp automation failed: {e}"}


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
