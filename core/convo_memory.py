"""
core/convo_memory.py
--------------------
Long-term conversation memory, kept entirely on this computer.

The brain only sends the last few messages to the AI (to keep token use low).
Anything older used to be forgotten. Now, when messages drop out of that short
window they are condensed into one short line each and appended to a rolling
summary saved in data/convo_summary.json. The summary (capped in size) and the
most recent saved facts are added to the system prompt, so EV AI still knows
what you talked about earlier, even after a restart, without resending it all.

Nothing leaves your computer except the compact summary inside the normal AI
request. Credential-looking text is never stored (same filter as memory.py).
"""

import json
import sys
from pathlib import Path

MAX_CHARS = 1800      # size of the rolling summary sent with each request
MAX_FACTS = 15        # saved facts included in the prompt


def _file() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent.parent
    return root / "data" / "convo_summary.json"


def _enabled() -> bool:
    try:
        from core import user_prefs
        return bool(user_prefs.get("long_term_memory"))
    except Exception:
        return True


def _load() -> list[str]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        lines = data.get("lines", [])
        return [str(x) for x in lines] if isinstance(lines, list) else []
    except Exception:
        return []


def _save(lines: list[str]) -> None:
    try:
        f = _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"lines": lines}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def remember_dropped(messages: list[dict]) -> None:
    """Fold messages that fell out of the short-term window into the summary."""
    if not messages or not _enabled():
        return
    try:
        from core.memory import _looks_sensitive
    except Exception:
        def _looks_sensitive(_t):  # type: ignore
            return False
    lines = _load()
    for m in messages:
        text = m.get("content")
        if not isinstance(text, str) or not text.strip() or text.startswith("[Shared"):
            continue
        if _looks_sensitive(text):
            continue
        if m.get("role") == "user":
            lines.append("You: " + _short(text, 160))
        else:
            lines.append("EV: " + _short(text, 100))
    while lines and sum(len(x) + 1 for x in lines) > MAX_CHARS:
        lines.pop(0)
    _save(lines)


def prompt_block(store=None) -> str:
    """Text added to the system prompt: earlier-conversation summary + saved facts."""
    if not _enabled():
        return ""
    parts = []
    lines = _load()
    if lines:
        parts.append("Earlier conversation with this user (oldest first, condensed; use it only "
                     "when relevant, do not recite it):\n" + "\n".join(lines))
    if store is not None:
        try:
            facts = store.recall().get("memories", [])[:MAX_FACTS]
            if facts:
                parts.append("Things the user asked you to remember:\n" +
                             "\n".join(f"- {f['key']}: {f['value']}" for f in facts))
        except Exception:
            pass
    return ("\n\n" + "\n\n".join(parts)) if parts else ""


def clear() -> None:
    try:
        _file().unlink()
    except Exception:
        pass
