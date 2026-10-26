"""
core/pycache_cleaner.py
-------------------------
Deletes every __pycache__ folder under the project. Used two ways:
- On every launch (main.py), when "auto-delete __pycache__" is on in
  Settings, together with sys.dont_write_bytecode so Python doesn't just
  recreate them as the app imports its modules.
- Settings -> "Clear now", on demand.

Skips the virtual environment and other folders that aren't this
project's own code (their caches are harmless and deleting them just
slows the next import for no benefit). Never raises — a locked or
read-only cache folder is skipped, not fatal.
"""

import shutil
from pathlib import Path

_SKIP_DIRS = {"venv", ".venv", "env", ".git", "node_modules", "site-packages"}


def clear_pycache(root: Path) -> int:
    """Returns how many __pycache__ folders were removed."""
    removed = 0
    stack = [Path(root)]
    while stack:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or child.is_symlink():
                continue
            if child.name == "__pycache__":
                shutil.rmtree(child, ignore_errors=True)
                if not child.exists():
                    removed += 1
            elif child.name not in _SKIP_DIRS:
                stack.append(child)
    return removed
