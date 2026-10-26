"""
core/updater.py
-----------------
Self-update: Settings -> Check for updates -> "Install now".

How it stays safe:
  * The update must come from an https:// address (plain http only for
    localhost testing) and its SHA-256 must match the value published in
    version.json — a corrupted or swapped download is refused.
  * Only whitelisted code folders/files are ever written (same list as
    scripts/make_release.py). Your .env, data/, database/ and venv/ can
    never be touched, and any path that tries to escape the app folder
    (absolute, "..") makes the whole update fail before anything changes.
  * Every file that will be overwritten is first copied to
    data/update_backup/<old version>/ — if anything goes wrong half-way,
    those copies are restored automatically.
  * It only ever installs a NEWER version than the one running.

Trust: whoever controls UPDATE_CHECK_URL can change the code on every
copy that uses it. Only point it at a place you control.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ALLOWED_DIRS = {"core", "tools", "ui", "voice", "scripts", "assets"}
ALLOWED_FILES = {
    "main.py", "config.py", "app_version.py", "check_env.py", "requirements.txt", "CHANGELOG.md",
    "README.md", "RELEASE_NOTES.md", "LICENSE", ".env.example", ".gitignore",
    "boot.bat", "boot_debug.bat", "install_autostart.bat", "uninstall_autostart.bat",
}
_MAX_DOWNLOAD = 100_000_000   # 100 MB sanity cap
_MAX_UNPACKED = 300_000_000


class UpdateError(Exception):
    """A problem the user can be told about in plain words."""


def parse_version(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version or "")[:4]) or (0,)


def _check_url(url: str) -> None:
    lowered = url.lower()
    local = lowered.startswith(("http://127.0.0.1", "http://localhost"))
    if not (lowered.startswith("https://") or local):
        raise UpdateError("Updates must be downloaded over https://.")


def fetch_info(url: str) -> dict:
    """Reads version.json. Returns {version, url, notes, zip_url, sha256}."""
    _check_url(url)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "EV.AI"})
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read(50_000).decode("utf-8", "replace").strip()
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"Couldn't reach the update source: {e}") from e
    info = {"version": raw, "url": "", "notes": "", "zip_url": "", "sha256": ""}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for key in info:
                info[key] = str(data.get(key, "") or "")
    except ValueError:
        pass
    if not re.search(r"\d", info["version"]):
        raise UpdateError("The update source didn't contain a version number.")
    return info


def download(zip_url: str, expected_sha256: str, progress=None) -> Path:
    """Downloads the release zip to a temp file and verifies its SHA-256."""
    _check_url(zip_url)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256 or ""):
        raise UpdateError("This update has no checksum, so it can't be verified. Not installing.")
    digest = hashlib.sha256()
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    path = Path(handle.name)
    try:
        request = urllib.request.Request(zip_url, headers={"User-Agent": "EV.AI"})
        with urllib.request.urlopen(request, timeout=30) as response, handle:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                done += len(chunk)
                if done > _MAX_DOWNLOAD:
                    raise UpdateError("The download is far bigger than expected. Not installing.")
                digest.update(chunk)
                handle.write(chunk)
                if progress and total:
                    progress(done, total)
    except (urllib.error.URLError, OSError) as e:
        path.unlink(missing_ok=True)
        raise UpdateError(f"The download failed: {e}") from e
    except UpdateError:
        path.unlink(missing_ok=True)
        raise
    if digest.hexdigest().lower() != expected_sha256.lower():
        path.unlink(missing_ok=True)
        raise UpdateError("The downloaded file doesn't match its checksum — it may be corrupted. Not installing.")
    return path


def _plan(zip_path: Path) -> list[tuple[str, str]]:
    """Validates the zip and returns [(name inside zip, relative target path)]
    for every file to write. Raises UpdateError if anything is not allowed."""
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise UpdateError("The update file isn't a valid zip.") from e
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if not infos:
            raise UpdateError("The update file is empty.")
        if sum(i.file_size for i in infos) > _MAX_UNPACKED:
            raise UpdateError("The update is far bigger than expected. Not installing.")
        names = [i.filename.replace("\\", "/") for i in infos]
        prefix = ""
        if all(n.startswith("EV_AI/") for n in names):
            prefix = "EV_AI/"
        plan = []
        for info, name in zip(infos, names):
            rel = name[len(prefix):]
            parts = rel.split("/")
            if rel.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", rel) or "" in parts:
                raise UpdateError(f"The update contains an unsafe path ({name}). Not installing.")
            top = parts[0]
            if len(parts) == 1:
                if top not in ALLOWED_FILES:
                    raise UpdateError(f"The update contains an unexpected file ({name}). Not installing.")
            elif top not in ALLOWED_DIRS:
                raise UpdateError(f"The update contains an unexpected folder ({name}). Not installing.")
            if rel.endswith((".pyc", ".pyo")) or "__pycache__" in parts:
                continue
            plan.append((info.filename, rel))
        if not any(rel == "main.py" for _, rel in plan):
            raise UpdateError("This doesn't look like an EV.AI release (no main.py). Not installing.")
        return plan


def install(zip_path: Path, app_root: Path, current_version: str) -> dict:
    """Backs up, then installs the release in `zip_path` over `app_root`.
    Returns {"files": n, "requirements_changed": bool, "backup": path}.
    On any failure the previous files are restored and UpdateError raised."""
    plan = _plan(zip_path)
    safe_version = re.sub(r"[^0-9A-Za-z._-]", "_", current_version or "old")
    backup_dir = app_root / "data" / "update_backup" / safe_version
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    req_path = app_root / "requirements.txt"
    old_req = req_path.read_bytes() if req_path.exists() else b""
    backed_up: list[str] = []
    created: list[Path] = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            for inner, rel in plan:
                target = app_root / rel
                if target.exists():
                    saved = backup_dir / rel
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
                    backed_up.append(rel)
                else:
                    created.append(target)
            for inner, rel in plan:
                target = app_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".evnew")
                with z.open(inner) as src, open(tmp, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                tmp.replace(target)
    except Exception as e:
        for rel in backed_up:                      # roll back
            try:
                shutil.copy2(backup_dir / rel, app_root / rel)
            except OSError:
                pass
        for path in created:
            path.unlink(missing_ok=True)
        for leftover in app_root.rglob("*.evnew"):
            leftover.unlink(missing_ok=True)
        raise UpdateError(f"The update couldn't be installed, so nothing was changed: {e}") from e

    new_req = req_path.read_bytes() if req_path.exists() else b""
    return {"files": len(plan), "requirements_changed": new_req != old_req, "backup": str(backup_dir)}


def install_requirements(app_root: Path) -> tuple[bool, str]:
    """pip install -r requirements.txt with this app's own Python."""
    python = Path(sys.executable)
    console_python = python.with_name("python.exe")
    if console_python.exists():
        python = console_python
    flags = 0x08000000 if sys.platform == "win32" else 0   # no console window
    try:
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(app_root / "requirements.txt")],
            capture_output=True, text=True, timeout=900, creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()[-400:]
    return True, ""


def check_and_install(url: str, current_version: str, app_root: Path, progress=None) -> dict:
    """Whole flow in one call (used by the UI's worker thread after the
    user confirms): returns {"version", "files", "requirements_ok", "note"}."""
    info = fetch_info(url)
    if parse_version(info["version"]) <= parse_version(current_version):
        raise UpdateError(f"You're already up to date ({current_version}).")
    if not info["zip_url"]:
        raise UpdateError("This update has no download link, so it can't be installed automatically.")
    zip_path = download(info["zip_url"], info["sha256"], progress)
    try:
        result = install(zip_path, app_root, current_version)
    finally:
        zip_path.unlink(missing_ok=True)
    requirements_ok, note = True, ""
    if result["requirements_changed"]:
        requirements_ok, note = install_requirements(app_root)
    return {"version": info["version"], "files": result["files"],
            "requirements_ok": requirements_ok, "note": note, "backup": result["backup"]}
