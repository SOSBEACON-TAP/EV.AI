"""
tools/memory.py
------------------
AI-facing memory tools — thin wrappers around core/memory.py's
MemoryStore, so the AI brain can remember/recall/forget things through
the normal tool-calling flow, same as any other tool.

get_store() returns a single shared MemoryStore instance — both these
tools and ui/main_window.py's "View Memory" quick-action button go
through this same instance, so reads and writes stay consistent no
matter which path they came from.
"""

from core.memory import MemoryStore

_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


def remember(category: str, key: str, value: str) -> dict:
    """Save a fact for later. category should be one of: preference,
    project, command, fact."""
    return get_store().remember(category, key, value)


def recall(category: str = "", key: str = "") -> dict:
    """Look up previously remembered things, optionally filtered by
    category and/or a search term in the key."""
    return get_store().recall(category or None, key or None)


def forget(key: str, category: str = "") -> dict:
    """Delete a specific remembered fact by key."""
    return get_store().forget(key, category or None)


def clear_memory(confirmed: bool = False) -> dict:
    """Delete ALL remembered facts. Requires confirmed=true — see
    core/router.py's registration of this tool and the confirmation
    policy in core/brain.py's SYSTEM_PROMPT."""
    if not confirmed:
        return {
            "confirmation_required": True,
            "message": "This will permanently delete everything EV remembers — preferences, project info, "
                       "and custom commands. Ask the user to confirm first.",
        }
    return get_store().clear_all()


def get_frequent_apps(limit: int = 5) -> dict:
    """List the applications the user opens most often."""
    return get_store().frequent_apps(limit)
