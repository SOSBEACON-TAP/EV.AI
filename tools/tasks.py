"""
tools/tasks.py
----------------
To-do list and notes (persistent — see core/personal_store.py). Items are
referred to by id (shown in the lists) or by words from their text, so
"mark milk as done" works as well as "complete item 3".
"""

from datetime import datetime

from core import personal_store as store


def _find(kind: str, which) -> dict | None:
    text = str(which).strip().lower()
    entries = store.items(kind)
    if text.isdigit():
        for entry in entries:
            if entry["id"] == int(text):
                return entry
    matches = [e for e in entries if text and text in e["text"].lower()]
    return matches[0] if len(matches) == 1 else None


def add_todo(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"error": "What should I add to the list?"}
    item = store.add("todos", text=text, done=False)
    return {"status": "added", "id": item["id"], "text": text}


def list_todos(include_done: bool = False) -> dict:
    todos = [t for t in store.items("todos") if include_done or not t.get("done")]
    return {"todos": [{"id": t["id"], "text": t["text"], "done": bool(t.get("done"))} for t in todos]}


def complete_todo(which: str) -> dict:
    item = _find("todos", which)
    if item is None:
        return {"error": f"I couldn't pick out exactly one to-do matching '{which}'. Try its number."}
    store.update("todos", item["id"], done=True)
    return {"status": "done", "id": item["id"], "text": item["text"]}


def remove_todo(which: str) -> dict:
    item = _find("todos", which)
    if item is None:
        return {"error": f"I couldn't pick out exactly one to-do matching '{which}'. Try its number."}
    store.remove("todos", item["id"])
    return {"status": "removed", "id": item["id"], "text": item["text"]}


def add_note(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"error": "What should the note say?"}
    item = store.add("notes", text=text)
    return {"status": "saved", "id": item["id"]}


def list_notes(limit: int = 10) -> dict:
    notes = store.items("notes")[-max(1, min(int(limit or 10), 50)):]
    return {"notes": [
        {"id": n["id"], "text": n["text"],
         "saved": datetime.fromtimestamp(n["created"]).strftime("%d %b %H:%M")}
        for n in reversed(notes)
    ]}


def delete_note(which: str) -> dict:
    item = _find("notes", which)
    if item is None:
        return {"error": f"I couldn't pick out exactly one note matching '{which}'. Try its number."}
    store.remove("notes", item["id"])
    return {"status": "deleted", "id": item["id"]}
