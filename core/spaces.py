"""
core/spaces.py
----------------
Mission Spaces: named workspaces (School, Coding, Gaming, Research, or your own) that open the right apps, websites and
folders in one go. "Snapshot" saves what is open right now as a new space, so you can come back to a project exactly as
you left it. Nothing is closed or deleted: a space only OPENS things.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_MAX = 30

DEFAULTS = {
    "School": {"apps": [], "urls": ["https://classroom.google.com", "https://docs.google.com"], "folders": [], "focus": True},
    "Coding": {"apps": ["code"], "urls": ["https://github.com"], "folders": [], "focus": True},
    "Gaming": {"apps": ["steam"], "urls": [], "folders": [], "focus": False},
    "Research": {"apps": [], "urls": ["https://scholar.google.com", "https://www.wikipedia.org"], "folders": [], "focus": True},
}


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _path() -> Path:
    return _root() / "data" / "spaces.json"


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return json.loads(json.dumps(DEFAULTS))


def _save(spaces: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(spaces, indent=2), encoding="utf-8")


def _find(spaces: dict, name: str) -> str | None:
    low = (name or "").strip().lower()
    for k in spaces:
        if k.lower() == low:
            return k
    for k in spaces:
        if low and low in k.lower():
            return k
    return None


def list_spaces() -> dict:
    """List the Mission Spaces and what each one opens."""
    sp = _load()
    return {"spaces": [{"name": k, "apps": v.get("apps", []), "urls": v.get("urls", []), "folders": v.get("folders", []),
                        "focus": bool(v.get("focus"))} for k, v in sp.items()]}


def save_space(name: str, apps: list | None = None, urls: list | None = None, folders: list | None = None,
               focus: bool = False) -> dict:
    """Create or replace a Mission Space."""
    name = " ".join((name or "").split())[:40]
    if not name:
        return {"error": "Give the space a name."}
    sp = _load()
    if name not in sp and len(sp) >= _MAX:
        return {"error": f"You already have {_MAX} spaces."}

    def clean(items, limit):
        return [str(i).strip()[:300] for i in (items or []) if str(i).strip()][:limit]
    sp[name] = {"apps": clean(apps, 20), "urls": clean(urls, 20), "folders": clean(folders, 20), "focus": bool(focus)}
    _save(sp)
    return {"status": "saved", "space": name}


def delete_space(name: str) -> dict:
    """Remove a Mission Space (only the saved list: nothing on the PC is touched)."""
    sp = _load()
    key = _find(sp, name)
    if key is None:
        return {"error": f"No space called '{name}'."}
    del sp[key]
    _save(sp)
    return {"status": "deleted", "space": key}


_SKIP = {"explorer", "ev_ai", "python", "pythonw", "searchhost", "startmenuexperiencehost", "textinputhost",
         "applicationframehost", "systemsettings", "shellexperiencehost", "lockapp", "widgets", "taskmgr"}


def open_programs() -> list[str]:
    """Names of the programs that have a visible window right now (for snapshots). Windows only."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        import psutil
        user32 = ctypes.windll.user32
        found: list[str] = []
        proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _l):
            if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    n = psutil.Process(pid.value).name()
                except Exception:
                    return True
                base = n[:-4] if n.lower().endswith(".exe") else n
                if base.lower() not in _SKIP and base not in found:
                    found.append(base)
            return True
        user32.EnumWindows(proto(cb), 0)
        return found[:15]
    except Exception:
        return []


def snapshot_space(name: str) -> dict:
    """Save the programs that are open right now as a new space (websites and folders are added by hand)."""
    apps = open_programs()
    if not apps:
        return {"error": "I couldn't see any open programs to save."}
    r = save_space(name, apps=apps)
    if "error" not in r:
        r["apps"] = apps
    return r


def start_space(name: str) -> dict:
    """Open everything a Mission Space lists. Nothing is closed."""
    sp = _load()
    key = _find(sp, name)
    if key is None:
        return {"error": f"No space called '{name}'. Spaces: " + ", ".join(sp) if sp else "No spaces saved yet."}
    space = sp[key]
    from tools import applications, browser, files
    opened, failed = [], []
    for a in space.get("apps", []):
        r = applications.open_application(a)
        (failed if "error" in r else opened).append(a)
    for u in space.get("urls", []):
        r = browser.open_website(u)
        (failed if "error" in r else opened).append(u)
    for f in space.get("folders", []):
        r = files.open_folder(f)
        (failed if "error" in r else opened).append(f)
    return {"status": "started", "space": key, "opened": opened, "failed": failed, "focus": bool(space.get("focus"))}
