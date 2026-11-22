"""
core/habits.py
----------------
Self-Evolving Shortcuts: EV notices what you keep doing and offers to turn it into a one-word shortcut (a saved task chain).
  - the same two actions in a row (within 90 s) three times  -> offers a two-step shortcut
  - the same opening action (app, site, folder) four times    -> offers a one-step shortcut
Nothing is created without your OK. Counts are saved in data/habits.json (tool names and short arguments only), and
anything not seen for 30 days is forgotten.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from config import APP_ROOT
from core import replay

_PATH = Path(APP_ROOT) / "data" / "habits.json"
_LOCK = threading.Lock()
_GAP = 90
_DAYS = 30
_ONE = {"open_application", "open_website", "open_folder", "start_mission_space", "open_youtube"}
_state = {"prev": None}


def _load() -> dict:
    try:
        d = json.loads(_PATH.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("counts", {})
            d.setdefault("dismissed", [])
            return d
    except (OSError, ValueError):
        pass
    return {"counts": {}, "dismissed": []}


def _save(d: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(d), encoding="utf-8")


def _step(name: str, args: dict) -> dict:
    return {"tool": name, "arguments": {k: v for k, v in (args or {}).items() if k != "confirmed"}}


def _sig(steps: list[dict]) -> str:
    return " > ".join(s["tool"] + json.dumps(s["arguments"], sort_keys=True) for s in steps)


def record(name: str, arguments: dict, ok: bool) -> None:
    if not ok or replay.is_readonly(name) or name in replay.NEVER:
        return
    try:
        now = time.time()
        cur = _step(name, arguments)
        cur = {**cur, "arguments": {k: str(v)[:200] for k, v in cur["arguments"].items()}}
        with _LOCK:
            d = _load()
            keys = []
            if name in _ONE:
                keys.append(([cur], _sig([cur])))
            prev = _state["prev"]
            if prev and now - prev[0] <= _GAP and prev[1] != cur:
                pair = [prev[1], cur]
                keys.append((pair, _sig(pair)))
            for steps, sig in keys:
                e = d["counts"].setdefault(sig, {"steps": steps, "n": 0, "last": now})
                e["n"] += 1
                e["last"] = now
            for sig in [k for k, v in d["counts"].items() if now - v["last"] > _DAYS * 86400]:
                d["counts"].pop(sig, None)
            _save(d)
            _state["prev"] = (now, cur)
    except Exception:
        pass


def _name_for(steps: list[dict]) -> str:
    bits = []
    for s in steps:
        a = s["arguments"]
        bits.append(str(next(iter(a.values()), s["tool"].replace("_", " ")))[:20])
    return " + ".join(bits)


def suggestions() -> list[dict]:
    """[{id, name, steps, n}] ready to be saved, most repeated first."""
    out = []
    with _LOCK:
        d = _load()
    for sig, e in d["counts"].items():
        need = 4 if len(e["steps"]) == 1 else 3
        if e["n"] >= need and sig not in d["dismissed"]:
            out.append({"id": sig, "name": _name_for(e["steps"]), "steps": e["steps"], "n": e["n"]})
    out.sort(key=lambda x: -x["n"])
    return out[:8]


def dismiss(sig: str) -> None:
    with _LOCK:
        d = _load()
        if sig not in d["dismissed"]:
            d["dismissed"].append(sig)
        _save(d)


def accept(router, sig: str, name: str) -> dict:
    """Turn a suggestion into a saved task chain. After this, 'run <name>' works by voice or text."""
    for s in suggestions():
        if s["id"] == sig:
            r = router.execute("save_task_chain", {"name": name, "steps_json": json.dumps(s["steps"]), "confirmed": True})
            if isinstance(r, dict) and r.get("status") == "saved":
                dismiss(sig)
            return r
    return {"error": "That suggestion is no longer there."}
