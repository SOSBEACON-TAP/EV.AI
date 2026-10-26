"""
core/updates.py
-----------------
"Check for updates": reads a small version file from UPDATE_CHECK_URL (in
.env) — either JSON like {"version": "1.2.0", "url": "https://...",
"notes": "..."} or just the version number as plain text — and compares
it with this app's version. With no URL set it says so plainly: EV.AI has
no built-in update server, so updates arrive as files you copy over.
"""

import json
import re
import urllib.error
import urllib.request


def _parse(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version or "")[:4]) or (0,)


def check(url: str, current: str) -> tuple[bool, str]:
    if not url:
        return True, ("No update source is set up. EV.AI updates arrive as zip files you copy over "
                      "the app folder — see Settings → Update log for what's changed.\n\n"
                      "If you're given a link to a version file, put it in .env as "
                      "UPDATE_CHECK_URL=… and this button will use it.")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "EV.AI"})
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read(20_000).decode("utf-8", "replace").strip()
    except (urllib.error.URLError, OSError) as e:
        return False, f"Couldn't reach the update source: {e}"
    latest, link, notes = raw, "", ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            latest = str(data.get("version", ""))
            link, notes = str(data.get("url", "")), str(data.get("notes", ""))
    except ValueError:
        pass
    if not re.search(r"\d", latest):
        return False, "The update source didn't contain a version number."
    if _parse(latest) > _parse(current):
        return True, (f"A newer version is available: {latest} (you have {current})."
                      + (f"\n\n{notes}" if notes else "") + (f"\n\nGet it: {link}" if link else ""))
    return True, f"You're up to date ({current})."
