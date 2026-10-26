"""
core/file_finder.py
---------------------
AI File Finder, local only. Keeps a small index of file NAMES, folders, sizes and
modification times in data/files.db (never file contents) and searches it with
plain-language requests:

    "find my EV AI python file"        "show me all images in Downloads"
    "the presentation I edited recently"   "find my Arduino projects"

A request is turned into safe filters (file type, folder, date, words to match)
by simple rules here — and the AI assistant can also pass those filters itself
through the search_files tool. Results are ranked by how well the words match
the file name and folder, with a boost for recently changed files.

No Qt in this module. The index is rebuilt in the background when it gets old.
"""

import math
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from config import APP_ROOT
from core import user_prefs

DB_PATH = APP_ROOT / "data" / "files.db"
MAX_FILES = 300_000
MAX_DEPTH = 10
STALE_HOURS = 12

_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "site-packages", "appdata",
              "$recycle.bin", "windows", "program files", "program files (x86)", "programdata", ".cache",
              ".idea", ".vscode", ".gradle", ".m2", ".npm", "dist-info", "system volume information"}

_BLOCKED_OPEN = {".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".msi", ".vbs", ".vbe", ".js", ".jse",
                 ".wsf", ".scr", ".reg", ".jar", ".hta", ".cpl", ".dll", ".lnk"}

_TYPE_WORDS = {
    "python": {".py", ".pyw", ".ipynb"}, "pdf": {".pdf"},
    "presentation": {".ppt", ".pptx", ".odp", ".key"}, "slide": {".ppt", ".pptx", ".odp", ".key"},
    "powerpoint": {".ppt", ".pptx"}, "ppt": {".ppt", ".pptx"},
    "document": {".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".pdf"}, "doc": {".doc", ".docx"},
    "word": {".doc", ".docx"}, "essay": {".doc", ".docx", ".odt", ".pdf"},
    "spreadsheet": {".xls", ".xlsx", ".csv", ".ods"}, "excel": {".xls", ".xlsx"}, "csv": {".csv"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".svg"},
    "photo": {".png", ".jpg", ".jpeg", ".heic", ".webp"}, "picture": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"},
    "screenshot": {".png", ".jpg", ".jpeg"}, "png": {".png"}, "jpg": {".jpg", ".jpeg"}, "jpeg": {".jpg", ".jpeg"},
    "video": {".mp4", ".mkv", ".mov", ".avi", ".webm"}, "movie": {".mp4", ".mkv", ".mov", ".avi"},
    "music": {".mp3", ".wav", ".flac", ".m4a", ".ogg"}, "audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg"},
    "song": {".mp3", ".wav", ".flac", ".m4a"}, "arduino": {".ino"}, "java": {".java"},
    "javascript": {".js", ".ts"}, "html": {".html", ".htm"}, "text": {".txt", ".md"},
    "zip": {".zip", ".rar", ".7z"}, "archive": {".zip", ".rar", ".7z"}, "notebook": {".ipynb"},
    "code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".cs", ".html", ".css", ".ino", ".go", ".rs"},
}
_FOLDER_WORDS = {"downloads": "downloads", "download": "downloads", "desktop": "desktop",
                 "documents": "documents", "pictures": "pictures", "videos": "videos", "music": "music"}
_STOP = set("""find show me my the a an all of in on from files file folder folders edited modified created
i that which where is please open search for with named called project projects latest recent recently
newest last today yesterday week month this some any get give list look looking everything anything stuff things""".split())


# ---------------------------------------------------------------- index ---------
def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, name TEXT, name_l TEXT, ext TEXT, "
                 "folder TEXT, folder_l TEXT, size INTEGER, mtime REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-\.]+", " ", text.lower()).strip()


def default_roots() -> list[Path]:
    home = Path.home()
    roots = [home / n for n in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]
    roots += [p for p in home.glob("OneDrive*") if p.is_dir()]
    roots.append(APP_ROOT)
    for extra in str(user_prefs.get("finder_folders")).split(";"):
        if extra.strip():
            roots.append(Path(extra.strip()))
    seen, out = set(), []
    for r in roots:
        try:
            r = r.resolve()
        except OSError:
            continue
        if r.is_dir() and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def build_index(budget_s: float = 90.0, roots: list | None = None) -> dict:
    """Scan the folders and rebuild the index. Returns {"files": n, "seconds": s, "partial": bool}."""
    started = time.time()
    rows, partial = [], False
    stack = [(Path(r), 0) for r in (roots or default_roots())]
    while stack:
        if time.time() - started > budget_s or len(rows) >= MAX_FILES:
            partial = True
            break
        folder, depth = stack.pop()
        try:
            with os.scandir(folder) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < MAX_DEPTH and entry.name.lower() not in _SKIP_DIRS \
                                    and not entry.name.startswith("."):
                                stack.append((Path(entry.path), depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            st = entry.stat()
                            name = entry.name
                            ext = os.path.splitext(name)[1].lower()
                            rows.append((entry.path, name, _norm(name), ext, str(folder), _norm(str(folder)),
                                         st.st_size, st.st_mtime))
                    except OSError:
                        continue
        except OSError:
            continue
    conn = _connect()
    try:
        conn.execute("DELETE FROM files")
        conn.executemany("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('indexed_at', ?)", (str(time.time()),))
        conn.commit()
    finally:
        conn.close()
    return {"files": len(rows), "seconds": round(time.time() - started, 1), "partial": partial}


def index_info() -> tuple[int, float | None]:
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        row = conn.execute("SELECT value FROM meta WHERE key='indexed_at'").fetchone()
    finally:
        conn.close()
    return count, (float(row[0]) if row else None)


def ensure_index(max_age_hours: float = STALE_HOURS, budget_s: float = 25.0) -> None:
    count, when = index_info()
    if count == 0 or when is None or (time.time() - when) > max_age_hours * 3600:
        build_index(budget_s)


# ------------------------------------------------------------ query parsing -------
def parse_query(text: str) -> dict:
    """Plain words -> filters: {"tokens", "exts", "folder", "since", "newest", "projects"}."""
    t = " " + (text or "").lower() + " "
    now = datetime.now()
    since, newest = None, False
    for pattern, delta in ((r"\btoday\b", timedelta(hours=now.hour, minutes=now.minute)),
                           (r"\byesterday\b", timedelta(days=1, hours=now.hour)),
                           (r"\b(this|past|last) week\b", timedelta(days=14 if "last week" in t else 7)),
                           (r"\b(this|past|last) month\b", timedelta(days=31))):
        if re.search(pattern, t):
            since = (now - delta).timestamp()
            t = re.sub(pattern, " ", t)
            break
    if re.search(r"\b(latest|newest|recent|recently|last)\b", t):
        newest = True
        if since is None and re.search(r"\brecent(ly)?\b", t):
            since = (now - timedelta(days=21)).timestamp()
    projects = bool(re.search(r"\bprojects?\b", t))
    exts, folder = set(), None
    words = re.findall(r"[a-z0-9\+\#]+", t)
    tokens = []
    for w in words:
        base = w[:-1] if w.endswith("s") and len(w) > 3 else w
        if w in _FOLDER_WORDS or base in _FOLDER_WORDS:
            folder = _FOLDER_WORDS.get(w) or _FOLDER_WORDS[base]
            continue
        if w in _TYPE_WORDS or base in _TYPE_WORDS:
            exts |= _TYPE_WORDS.get(w) or _TYPE_WORDS[base]
            continue
        if w in _STOP or len(w) < 2:
            continue
        tokens.append(w)
    return {"tokens": tokens, "exts": exts, "folder": folder, "since": since, "newest": newest,
            "projects": projects}


# ------------------------------------------------------------------- search -------
LAST_RESULTS: list[dict] = []


def _score(row, tokens, newest_boost: bool, now: float) -> float:
    _path, _name, name_l, _ext, _folder, folder_l, _size, mtime = row
    score = 0.0
    name_words = name_l.split()
    for tok in tokens:
        if tok in name_l:
            score += 3.0
        elif folder_l and tok in folder_l:
            score += 1.0
        else:
            best = max((SequenceMatcher(None, tok, w).ratio() for w in name_words), default=0.0)
            if best >= 0.82:
                score += 2.0
    age_days = max(0.0, (now - mtime) / 86400.0)
    score += (2.0 if newest_boost else 0.6) / (1.0 + age_days / 30.0)
    return score


def search(query: str = "", file_types: list | None = None, folder: str = "", days: int = 0,
           limit: int = 10, folders_only: bool | None = None) -> dict:
    """Find files. `query` is plain language; the other arguments are optional exact filters
    (file_types like ['.py', 'pdf'], a folder name or path fragment, modified within `days`)."""
    ensure_index()
    f = parse_query(query)
    exts = set(f["exts"])
    for t in file_types or []:
        t = t.strip().lower()
        if t:
            exts.add(t if t.startswith(".") else "." + t)
    since = f["since"]
    if days and days > 0:
        since = (datetime.now() - timedelta(days=days)).timestamp()
    folder_hint = _norm(folder) if folder else f["folder"]
    tokens = [_norm(t) for t in f["tokens"] if _norm(t)]
    want_folders = f["projects"] if folders_only is None else folders_only

    sql, args = "SELECT path,name,name_l,ext,folder,folder_l,size,mtime FROM files WHERE 1=1", []
    if exts:
        sql += " AND ext IN (%s)" % ",".join("?" * len(exts))
        args += sorted(exts)
    if since:
        sql += " AND mtime >= ?"
        args.append(since)
    if folder_hint:
        sql += " AND folder_l LIKE ?"
        args.append(f"%{folder_hint}%")
    conn = _connect()
    try:
        rows = []
        if tokens:
            like = " OR ".join(["name_l LIKE ? OR folder_l LIKE ?"] * len(tokens))
            targs = [p for t in tokens for p in (f"%{t}%", f"%{t}%")]
            rows = conn.execute(sql + f" AND ({like}) LIMIT 8000", args + targs).fetchall()
            if len(rows) < 5:           # typos: look at every name that passes the other filters
                rows = conn.execute(sql + " LIMIT 60000", args).fetchall()
        else:
            rows = conn.execute(sql + " ORDER BY mtime DESC LIMIT 8000", args).fetchall()
    finally:
        conn.close()

    now = time.time()
    scored = [(_score(r, tokens, f["newest"], now), r) for r in rows]
    if tokens:
        scored = [(s, r) for s, r in scored if s >= 1.0 + 0.0]           # needs some word match
        scored = [(s, r) for s, r in scored if _has_match(r, tokens)]
    scored.sort(key=lambda x: (-x[0], -x[1][7]))

    results: list[dict] = []
    if want_folders:
        groups: dict[str, dict] = {}
        for s, r in scored[:3000]:
            g = groups.setdefault(r[4], {"score": 0.0, "count": 0, "mtime": 0.0})
            g["score"] = max(g["score"], s)
            g["count"] += 1
            g["mtime"] = max(g["mtime"], r[7])
        ranked = sorted(groups.items(), key=lambda kv: (-(kv[1]["score"] + 0.3 * math.log(1 + kv[1]["count"])),
                                                        -kv[1]["mtime"]))
        for path, g in ranked[:limit]:
            results.append({"name": Path(path).name or path, "path": path, "folder": str(Path(path).parent),
                            "is_dir": True, "size": 0, "mtime": g["mtime"], "files": g["count"]})
    else:
        for s, r in scored[:limit]:
            results.append({"name": r[1], "path": r[0], "folder": r[4], "is_dir": False, "size": r[6], "mtime": r[7]})

    for i, item in enumerate(results, 1):
        item["n"] = i
        item["modified"] = datetime.fromtimestamp(item["mtime"]).strftime("%Y-%m-%d %H:%M") if item["mtime"] else ""
    LAST_RESULTS[:] = results
    count, when = index_info()
    return {"query": query, "count": len(results), "results": results, "indexed_files": count,
            "filters": {"types": sorted(exts), "folder": folder_hint or "", "newest": f["newest"],
                        "words": tokens, "folders_only": want_folders}}


def _has_match(row, tokens) -> bool:
    name_l, folder_l = row[2], row[5]
    words = name_l.split()
    for tok in tokens:
        if tok in name_l or tok in folder_l:
            return True
        if any(SequenceMatcher(None, tok, w).ratio() >= 0.82 for w in words):
            return True
    return False


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n} B"


# --------------------------------------------------------------------- open -------
def open_path(path: str, reveal: bool = False) -> dict:
    """Open a file (or reveal it in its folder). Programs and scripts are never launched from here."""
    p = Path(path)
    if not p.exists():
        return {"error": f"That file no longer exists: {path}"}
    try:
        if p.is_file() and (reveal or p.suffix.lower() in _BLOCKED_OPEN):
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p.parent)])
            note = "" if reveal else "Programs and scripts aren't launched from search, so I showed it in its folder."
            return {"status": "showed in folder", "path": str(p), "note": note}
        if sys.platform == "win32":
            os.startfile(str(p))          # noqa: S606 - user-chosen document/folder
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return {"status": "opened", "path": str(p)}
    except OSError as e:
        return {"error": f"Couldn't open it: {e}"}


def open_result(number: int, reveal: bool = False) -> dict:
    if not LAST_RESULTS:
        return {"error": "There are no search results to open yet. Ask me to find something first."}
    if not 1 <= number <= len(LAST_RESULTS):
        return {"error": f"Pick a result between 1 and {len(LAST_RESULTS)}."}
    item = LAST_RESULTS[number - 1]
    out = open_path(item["path"], reveal=reveal and not item["is_dir"])
    out["which"] = f"#{number}: {item['name']}"
    return out
