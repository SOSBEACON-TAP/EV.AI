"""
core/chatsorter.py
------------------
Optional long-term memory through ChatSorter (https://chatsorter.com, API based).
OFF by default. When it is switched on in Settings and CHATSORTER_API_KEY is set:
  * every message you send is stored (in the background, never slows a reply), and
  * before each AI reply, relevant memories are fetched and added to the prompt.
Messages that look like passwords or keys are never sent. Your messages go to
ChatSorter's servers when this is on, which is why it is opt-in.
Any error or slow answer is ignored, EV AI just carries on without it.
"""

import json
import os
import threading
import urllib.request
import uuid

from core import user_prefs

API = "https://api.chatsorter.com"
SEARCH_TIMEOUT = 2.5     # seconds; never hold up a reply longer than this


def enabled() -> bool:
    return bool(user_prefs.get("chatsorter_enabled")) and bool(os.getenv("CHATSORTER_API_KEY", "").strip())


def _chat_id() -> str:
    cid = user_prefs.get("chatsorter_chat_id")
    if not cid:
        cid = "ev-" + uuid.uuid4().hex[:16]
        user_prefs.set_value("chatsorter_chat_id", cid)
    return cid


def _post(path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {os.getenv('CHATSORTER_API_KEY', '').strip()}",
                 "Content-Type": "application/json", "User-Agent": "EV.AI"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _sensitive(text: str) -> bool:
    try:
        from core.memory import _looks_sensitive
        return _looks_sensitive(text)
    except Exception:
        return False


def store_async(message: str) -> None:
    if not enabled() or _sensitive(message):
        return

    def run():
        try:
            _post("/process", {"chat_id": _chat_id(), "message": message[:2000]}, 15)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def memories_block(query: str) -> str:
    """Prompt text with relevant memories, or '' (also on any error or timeout)."""
    if not enabled() or _sensitive(query):
        return ""
    try:
        data = _post("/search", {"chat_id": _chat_id(), "query": query[:500]}, SEARCH_TIMEOUT)
        items = [m.get("summary", "") for m in (data.get("memories") or []) if m.get("summary")][:6]
    except Exception:
        return ""
    if not items:
        return ""
    return ("\n\nRelevant things remembered from earlier chats (use only if relevant):\n" +
            "\n".join(f"- {t}" for t in items))
