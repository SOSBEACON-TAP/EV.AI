"""
tools/files.py
----------------
Folder and file tools: open folders in Explorer, create folders, list a
folder's contents, find files by name, and read a text file's contents.

Stage 8 adds move/copy/rename and delete. move/copy/rename are
reversible-ish (the file still exists somewhere) so they run without
confirmation, same as create_folder always has. delete_file is
genuinely destructive and requires_confirmation=True in core/router.py,
same pattern as close_application and clear_memory — it refuses to run
until the AI passes confirmed=true, which it should only do after the
user has explicitly agreed in conversation.
"""

import os
import shutil
import sys
from pathlib import Path

_SHORTCUTS = {
    "downloads": lambda: Path.home() / "Downloads",
    "desktop": lambda: Path.home() / "Desktop",
    "documents": lambda: Path.home() / "Documents",
    "pictures": lambda: Path.home() / "Pictures",
    "home": lambda: Path.home(),
}


def _resolve_path(path: str) -> Path:
    key = path.strip().lower()
    if key in _SHORTCUTS:
        return _SHORTCUTS[key]()
    return Path(os.path.expandvars(os.path.expanduser(path)))


def open_folder(path: str) -> dict:
    """Open a folder in File Explorer. Accepts shortcuts like
    'downloads', 'desktop', 'documents', or a full path."""
    target = _resolve_path(path)
    if not target.exists() or not target.is_dir():
        return {"error": f"Folder not found: {path}"}
    if sys.platform != "win32":
        return {"error": "Opening folders is only implemented for Windows right now."}
    os.startfile(str(target))
    return {"status": "opened", "path": str(target)}


def create_folder(path: str) -> dict:
    """Create a new folder, including any missing parent folders."""
    target = _resolve_path(path)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {"error": f"Could not create folder: {e}"}
    return {"status": "created", "path": str(target)}


def find_files(name: str, search_path: str = "home") -> dict:
    """Search for files whose name contains `name` (case-insensitive),
    starting from search_path (defaults to the user's home folder).
    Capped at 20 results so a broad search can't return an enormous
    list back to the AI."""
    root = _resolve_path(search_path)
    if not root.exists():
        return {"error": f"Search location not found: {search_path}"}

    matches = []
    needle = name.lower()
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fname in filenames:
                if needle in fname.lower():
                    matches.append(str(Path(dirpath) / fname))
                    if len(matches) >= 20:
                        return {"matches": matches, "truncated": True}
    except PermissionError:
        pass  # skip folders we can't read rather than failing the whole search

    return {"matches": matches, "truncated": False}


def list_folder(path: str = "home") -> dict:
    """List the immediate contents of a folder (not recursive). Accepts
    the same shortcuts as open_folder. Capped at 100 entries."""
    target = _resolve_path(path)
    if not target.exists() or not target.is_dir():
        return {"error": f"Folder not found: {path}"}
    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError as e:
        return {"error": f"Could not list folder: {e}"}

    items = [
        {"name": p.name, "type": "folder" if p.is_dir() else "file"}
        for p in entries[:100]
    ]
    return {"path": str(target), "items": items, "truncated": len(entries) > 100}


def _resolve_two(src: str, dst: str) -> tuple[Path, Path] | dict:
    source = _resolve_path(src)
    if not source.exists():
        return {"error": f"Source not found: {src}"}
    return source, _resolve_path(dst)


def move_file(src: str, dst: str) -> dict:
    """Move (or rename, if dst is a new name in the same folder) a file
    or folder from src to dst."""
    resolved = _resolve_two(src, dst)
    if isinstance(resolved, dict):
        return resolved
    source, dest = resolved
    try:
        if dest.is_dir():
            dest = dest / source.name
        shutil.move(str(source), str(dest))
    except OSError as e:
        return {"error": f"Could not move: {e}"}
    return {"status": "moved", "from": str(source), "to": str(dest)}


def copy_file(src: str, dst: str) -> dict:
    """Copy a file or folder from src to dst, leaving the original in place."""
    resolved = _resolve_two(src, dst)
    if isinstance(resolved, dict):
        return resolved
    source, dest = resolved
    try:
        if dest.is_dir():
            dest = dest / source.name
        if source.is_dir():
            shutil.copytree(str(source), str(dest))
        else:
            shutil.copy2(str(source), str(dest))
    except OSError as e:
        return {"error": f"Could not copy: {e}"}
    return {"status": "copied", "from": str(source), "to": str(dest)}


def rename_file(path: str, new_name: str) -> dict:
    """Rename a file or folder in place (keeps it in the same parent folder)."""
    target = _resolve_path(path)
    if not target.exists():
        return {"error": f"Not found: {path}"}
    if "/" in new_name or "\\" in new_name:
        return {"error": "new_name must be a plain name, not a path."}
    dest = target.parent / new_name
    try:
        target.rename(dest)
    except OSError as e:
        return {"error": f"Could not rename: {e}"}
    return {"status": "renamed", "from": str(target), "to": str(dest)}


def delete_file(path: str, confirmed: bool = False) -> dict:
    """Permanently delete a file or folder (folders are removed with
    their full contents). Genuinely destructive and irreversible — see
    core/router.py's requires_confirmation=True on this tool."""
    if not confirmed:
        return {
            "confirmation_required": True,
            "message": f"This will permanently delete '{path}'. Ask the user to confirm first.",
        }
    target = _resolve_path(path)
    if not target.exists():
        return {"error": f"Not found: {path}"}
    try:
        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
    except OSError as e:
        return {"error": f"Could not delete: {e}"}
    return {"status": "deleted", "path": str(target)}


def read_text_file(path: str, max_chars: int = 4000) -> dict:
    """Read a text file's contents, capped at max_chars so a huge file
    doesn't blow up the AI's context window. Not for binaries, PDFs,
    or images — plain text only."""
    target = _resolve_path(path)
    if not target.exists() or not target.is_file():
        return {"error": f"File not found: {path}"}
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"error": f"Could not read file: {e}"}

    truncated = len(content) > max_chars
    return {"content": content[:max_chars], "truncated": truncated, "path": str(target)}
