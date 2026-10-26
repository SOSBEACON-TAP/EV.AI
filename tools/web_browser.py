"""
tools/web_browser.py
-----------------------
Stage 9: a browser EV AI can actually navigate on spoken command —
"search google for X", "click the second result", "type my name",
"scroll down", "go back" — rather than just opening a URL and leaving
it (that's what tools/browser.py's open_website already does; this
module is for staying in control of a live page across several
commands in a row).

Built on the same persistent-Playwright-session pattern as
tools/whatsapp.py, with its own separate browser profile/window
(config.settings.BROWSER_PROFILE_DIR) so it stays signed into whatever
sites you log into there, independent of the WhatsApp session.

No confirmation gate on any of these: navigating, clicking, and typing
here is the direct equivalent of the user doing it themselves with
their own mouse/keyboard, same trust level as open_website. EV AI isn't
a judge of which web pages are safe to click around on — exactly like
it would be if the user were driving the browser by hand.
"""

from config import settings

_playwright = None
_browser_context = None
_page = None


def _ensure_page():
    """Lazily launches (once) a persistent Chromium context, reused
    across calls. Returns the Page, or raises RuntimeError with a
    message meant to be shown to the user."""
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

    profile_dir = settings.browser_profile_path
    profile_dir.mkdir(parents=True, exist_ok=True)

    if _playwright is None:
        _playwright = sync_playwright().start()

    _browser_context = _playwright.chromium.launch_persistent_context(
        str(profile_dir), headless=False, viewport={"width": 1280, "height": 860},
    )
    _page = _browser_context.pages[0] if _browser_context.pages else _browser_context.new_page()
    return _page


def browser_search_google(query: str) -> dict:
    """Search Google for `query` in the controlled browser window."""
    try:
        page = _ensure_page()
        page.goto(f"https://www.google.com/search?q={query}", timeout=30_000)
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not search: {e}"}
    return {"status": "searched", "query": query}


def browser_open(url: str) -> dict:
    """Navigate the controlled browser window to a URL or bare domain."""
    target = url if "://" in url else f"https://{url}"
    try:
        page = _ensure_page()
        page.goto(target, timeout=30_000)
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not open '{url}': {e}"}
    return {"status": "opened", "url": target}


def browser_click(text: str) -> dict:
    """Click the first visible link/button/element whose text contains `text`."""
    try:
        page = _ensure_page()
        page.get_by_text(text, exact=False).first.click(timeout=10_000)
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not click '{text}': {e}"}
    return {"status": "clicked", "text": text}


def browser_type(text: str) -> dict:
    """Type into whatever input/textbox currently has focus on the page."""
    try:
        page = _ensure_page()
        page.keyboard.type(text, delay=20)
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not type: {e}"}
    return {"status": "typed", "length": len(text)}


def browser_press_enter() -> dict:
    """Press Enter on the page — e.g. to submit a search box or form."""
    try:
        page = _ensure_page()
        page.keyboard.press("Enter")
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not press Enter: {e}"}
    return {"status": "pressed"}


def browser_scroll(direction: str = "down") -> dict:
    """Scroll the page up or down."""
    try:
        page = _ensure_page()
        delta = 600 if direction.lower() != "up" else -600
        page.mouse.wheel(0, delta)
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not scroll: {e}"}
    return {"status": "scrolled", "direction": direction}


def browser_go_back() -> dict:
    """Go back to the previous page in the controlled browser window."""
    try:
        page = _ensure_page()
        page.go_back(timeout=10_000)
    except RuntimeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not go back: {e}"}
    return {"status": "went_back"}


def close_browser_session() -> dict:
    """Closes the controlled browser window, if one is open."""
    global _browser_context, _page
    if _browser_context is not None:
        _browser_context.close()
        _browser_context = None
        _page = None
        return {"status": "closed"}
    return {"status": "not_open"}
