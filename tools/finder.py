"""
tools/finder.py
-----------------
AI-facing tools for the File Finder: search the local file-name index with plain
language and open a result by its number ("open the second one"). Opening only
ever hands a document/folder to Windows' normal "open" — programs and scripts
are shown in their folder instead of launched.
"""

from core import file_finder


def search_files(query: str = "", file_types: str = "", folder: str = "", days: int = 0) -> dict:
    """Find files by plain-language description and/or filters."""
    types = [t for t in (file_types or "").replace(";", ",").split(",") if t.strip()]
    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        days = 0
    result = file_finder.search(query=query, file_types=types, folder=folder or "", days=days, limit=10)
    items = [{"number": r["n"], "name": r["name"], "location": r["folder"] if not r["is_dir"] else r["path"],
              "modified": r["modified"], "size": "" if r["is_dir"] else file_finder.human_size(r["size"]),
              "type": "folder" if r["is_dir"] else "file"} for r in result["results"]]
    if not items:
        return {"count": 0, "message": "No matching files found. Try other words, or refresh the file index "
                                       "in the File Finder window.", "filters": result["filters"]}
    return {"count": len(items), "results": items,
            "hint": "Tell the user the best matches with their folders. They can ask to 'open the second result'."}


def open_search_result(number: int, show_in_folder: bool = False) -> dict:
    """Open result #number from the most recent search (or show it in its folder)."""
    try:
        number = int(number)
    except (TypeError, ValueError):
        return {"error": "Give the result number, like 2."}
    return file_finder.open_result(number, reveal=bool(show_in_folder))
