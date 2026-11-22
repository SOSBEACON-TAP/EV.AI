"""
core/replay.py
----------------
Action Replay: EV remembers the last things it did (grouped into "runs" when they happen close together) and can do the same
run again, step by step. Look-ups are not recorded, sends and deletes are never replayed (they need your OK again), and
anything that asks for confirmation or is above your trust level still asks. Saved to data/replay.json (last 40 steps).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from config import APP_ROOT

_PATH = Path(APP_ROOT) / "data" / "replay.json"
_LOCK = threading.Lock()
_MAX = 40
_GAP = 90          # seconds of quiet that start a new run
_SECRET = ("password", "passwd", "secret", "token", "key", "pin")
NEVER = {"send_email", "send_whatsapp_message", "delete_file", "clear_memory", "close_application", "lock_computer",
         "replay_last_actions", "run_task_chain", "save_task_chain"}
_READ = ("get_", "list_", "read_", "check_", "search_", "find_", "recall", "calculate", "convert_", "date_math", "world_time",
         "roll_dice", "pick_random", "text_stats", "morning_briefing", "open_search_result", "suggest_")


def is_readonly(name: str) -> bool:
    return name.startswith(_READ)


def _load() -> list[dict]:
    try:
        d = json.loads(_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def record(name: str, arguments: dict, ok: bool) -> None:
    if not ok or is_readonly(name):
        return
    try:
        args = {k: (str(v)[:400] if not isinstance(v, (int, float, bool)) else v)
                for k, v in (arguments or {}).items()
                if k != "confirmed" and not any(w in k.lower() for w in _SECRET)}
        with _LOCK:
            items = _load()
            items.append({"t": time.time(), "tool": name, "args": args})
            items = items[-_MAX:]
            _PATH.parent.mkdir(parents=True, exist_ok=True)
            _PATH.write_text(json.dumps(items), encoding="utf-8")
    except Exception:
        pass


def runs(limit: int = 6) -> list[list[dict]]:
    """Newest run first; each run is a list of steps in the order they happened."""
    with _LOCK:
        items = _load()
    out: list[list[dict]] = []
    for it in items:
        if out and it["t"] - out[-1][-1]["t"] <= _GAP:
            out[-1].append(it)
        else:
            out.append([it])
    return list(reversed(out))[:limit]


def label(run: list[dict]) -> str:
    names = [s["tool"].replace("_", " ") for s in run]
    when = time.strftime("%H:%M", time.localtime(run[0]["t"]))
    return f"{when}  ·  " + "  →  ".join(names[:4]) + (f"  (+{len(names) - 4})" if len(names) > 4 else "")


def replay(router, run: list[dict], progress=None) -> list[str]:
    """Do a run again. Returns one line per step."""
    from core import thoughts
    lines = []
    for s in run:
        name, args = s["tool"], dict(s.get("args") or {})
        if name in NEVER:
            lines.append(f"skipped {name} (needs your OK each time)")
            continue
        tool = router.get(name)
        if tool is None:
            lines.append(f"skipped {name} (not available)")
            continue
        try:
            thoughts.add("note", f"Replaying: {name}")
            r = router.execute(name, args)
            if isinstance(r, dict) and r.get("confirmation_required"):
                lines.append(f"{name}: waiting for your OK (raise trust or do it by hand)")
            elif isinstance(r, dict) and r.get("error"):
                lines.append(f"{name}: failed - {r['error']}")
            else:
                lines.append(f"{name}: done")
        except Exception as e:
            lines.append(f"{name}: failed - {e}")
        if progress:
            progress(lines[-1])
        time.sleep(0.4)
    return lines
