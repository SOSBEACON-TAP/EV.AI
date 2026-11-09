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
import os
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


# ---------------------------------------------------------------------------
# Packaged (.exe) version: download the full Windows zip, then a small helper
# script swaps the files after EV AI closes and starts it again.
# ---------------------------------------------------------------------------
PENDING_SCRIPT: "Path | None" = None
_MAX_EXE_DOWNLOAD = 1_500_000_000


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _download_big(zip_url: str, expected_sha256: str, progress=None) -> Path:
    global _MAX_DOWNLOAD
    old = _MAX_DOWNLOAD
    _MAX_DOWNLOAD = _MAX_EXE_DOWNLOAD
    try:
        return download(zip_url, expected_sha256, progress)
    finally:
        _MAX_DOWNLOAD = old


def wait_until_unlocked(path: Path, seconds: int = 90) -> bool:
    """True once `path` can be opened for reading. A freshly unpacked .exe is often held for 10-60 s while the
    antivirus (Windows Defender's cloud check, for instance) looks at it; copying it then fails with
    'being used by another process'. Waiting here, before anything is swapped, avoids a failed update."""
    import time
    end = time.monotonic() + seconds
    while True:
        try:
            with open(path, "rb") as f:
                f.read(1)
            return True
        except OSError:
            if time.monotonic() >= end:
                return False
            time.sleep(1)


def stage_frozen(zip_path: Path, app_root: Path) -> Path:
    """Unpacks the Windows zip next to the app and writes the swap script."""
    global PENDING_SCRIPT
    stage = app_root / "data" / "update_stage"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as z:
            root = stage.resolve()
            for member in z.namelist():
                if not (stage / member).resolve().is_relative_to(root):
                    raise UpdateError("The update contains an unsafe path. Not installing.")
            z.extractall(stage)
    except zipfile.BadZipFile as e:
        raise UpdateError("The downloaded update is not a valid zip file.") from e
    # The zip may hold the app at EV_AI/ or dist/EV_AI/: use whichever folder has the exe.
    exes = sorted(stage.rglob("EV_AI.exe"), key=lambda p: len(p.parts))
    if not exes:
        raise UpdateError("The update doesn't contain EV_AI.exe. Not installing.")
    new_dir = exes[0].parent
    wait_until_unlocked(exes[0], 90)       # antivirus may be scanning the new program: let it finish BEFORE we start swapping
    script = app_root / "data" / "apply_update.bat"
    exe = Path(sys.executable).resolve()
    pid = os.getpid()
    log = app_root / "data" / "update_log.txt"
    ps_exe = str(exe).replace("'", "''")
    kill_mine = ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Process -Name EV_AI -ErrorAction '
                 f"SilentlyContinue | Where-Object {{ $_.Path -eq '{ps_exe}' }} | Stop-Process -Force\" >nul 2>&1")
    busy = app_root / "data" / "update_busy.txt"
    root_ps = str(app_root).replace("'", "''")
    _holders = (f"Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $_.Id -ne $PID -and "
                f"@('explorer','cmd','powershell','conhost') -notcontains $_.ProcessName -and "
                f"( ($_.Path -and $_.Path -like '{root_ps}\\*') -or "
                f"($_.Modules | Where-Object {{ $_.FileName -like '{root_ps}\\*' }} | Select-Object -First 1) ) }}")
    holders_list = f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{_holders} | ForEach-Object {{ \'  \' + $_.ProcessName + \' \' + $_.Id }}"'
    kill_holders = (f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{_holders} | ForEach-Object {{ \'  closed \' + '
                    f'$_.ProcessName + \' \' + $_.Id; $_ | Stop-Process -Force }}"')
    move_files_ps = (
        f"$src='{root_ps}\\_internal'; $dst='{root_ps}\\_internal.old'; "
        "New-Item -ItemType Directory -Force -Path $dst | Out-Null; "
        "Get-ChildItem -LiteralPath $src -Recurse -File -Force | ForEach-Object { "
        "$t = Join-Path $dst $_.FullName.Substring($src.Length + 1); "
        "New-Item -ItemType Directory -Force -Path (Split-Path $t) | Out-Null; "
        "Move-Item -LiteralPath $_.FullName -Destination $t -Force }; "
        "$left = @(Get-ChildItem -LiteralPath $src -Recurse -File -Force).Count; "
        "Write-Output ('files left in the old folder: ' + $left); if ($left -gt 0) { exit 1 }")
    stage_exe = str(new_dir / "EV_AI.exe").replace("'", "''")
    wait_stage = ("powershell -NoProfile -ExecutionPolicy Bypass -Command \"$f='" + stage_exe + "'; "
                  "for ($i=0; $i -lt 90; $i++) { try { $s=[IO.File]::Open($f,'Open','ReadWrite','None'); $s.Close(); "
                  "'new program ready after ' + $i + ' s'; exit 0 } catch { Start-Sleep -Seconds 1 } }; "
                  "'new program is still locked (antivirus?), trying anyway'; exit 0\"")
    move_files = f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{move_files_ps}"'
    internal, internal_old, new_internal = app_root / "_internal", app_root / "_internal.old", new_dir / "_internal"
    lines = [
        "@echo off",
        'cd /d "%TEMP%"',                      # the helper itself must not hold the app folder open
        f'echo Helper started %date% %time% waiting for EV AI (PID {pid}) to close > "{log}"',
        f'echo busy > "{busy}"',
        "set /a n=0",
        ":wait",
        # Wait until NO EV_AI.exe is running (EV AI can leave helper processes behind that keep files locked).
        'tasklist /FI "IMAGENAME eq EV_AI.exe" 2>nul | find /I "EV_AI.exe" >nul',
        "if errorlevel 1 goto go",
        "set /a n+=1",
        "if %n% EQU 3 (",
        f'  echo Still running after 3 checks, closing EV AI by its process id >> "{log}"',
        f"  taskkill /F /PID {pid} >nul 2>&1",
        ")",
        "if %n% EQU 6 (",
        f'  echo Still running after 6 checks, closing this copy of EV AI by its path >> "{log}"',
        f"  {kill_mine}",
        ")",
        # NOTE: never use /T here: the helper was started by EV AI, so killing the tree kills the helper.
        "if %n% GEQ 14 (",
        f'  echo Still running after 14 checks, closing every EV_AI.exe >> "{log}"',
        "  taskkill /F /IM EV_AI.exe >nul 2>&1",
        "  ping -n 4 127.0.0.1 >nul",
        "  goto go",
        ")",
        "ping -n 2 127.0.0.1 >nul",
        "goto wait",
        ":go",
        "ver >nul",
        f'echo EV AI closed after %n% checks, swapping in the new version >> "{log}"',
        f"{wait_stage} >> \"{log}\" 2>&1",
        # The big _internal folder is swapped by renaming (instant, same drive) instead of copying
        # thousands of files, so there is almost nothing that can fail halfway.
        # leftovers of an earlier update (a program that was still shutting down kept them locked)
        f'for /d %%D in ("{internal_old}*") do rd /s /q "%%D" >nul 2>&1',
        f'if exist "{internal_old}" move "{internal_old}" "{internal_old}.%random%" >nul 2>&1',
        f'if exist "{internal_old}" goto failed',
        "set mode=folder",
        # Windows refuses to rename a folder while ANY program still has a file in it open
        # (antivirus scan, a program that is slow to shut down, an Explorer window), so try a few times.
        "set /a t=0",
        ":trymove",
        f'if not exist "{internal}" goto moved',
        # (&& runs goto only when move succeeded; it does not rely on ERRORLEVEL)
        f'move "{internal}" "{internal_old}" >nul 2>&1 && goto moved',
        "set /a t+=1",
        "if %t% EQU 3 call :killholders",
        "if %t% GEQ 8 goto movefiles",
        "ping -n 3 127.0.0.1 >nul",
        "goto trymove",
        ":movefiles",
        # Plan B: a program that cannot be closed (stuck while shutting down) keeps the FOLDER locked, but
        # Windows still lets us RENAME the individual files it has loaded. Move every file out one by one.
        f'echo Folder is locked by a program that will not close. Moving the old files one by one instead >> "{log}"',
        f"{move_files} >> \"{log}\" 2>&1 || goto movefailed",
        "set mode=files",
        f'if not exist "{internal}" mkdir "{internal}"',
        f'if exist "{app_root}\\EV_AI.exe.old" del /f /q "{app_root}\\EV_AI.exe.old" >nul 2>&1',
        f'if exist "{app_root}\\EV_AI.exe" ren "{app_root}\\EV_AI.exe" EV_AI.exe.old >> "{log}" 2>&1',
        f'robocopy "{new_internal}" "{internal}" /E /R:5 /W:1 /NFL /NDL /NJH /NJS >> "{log}" 2>&1',
        "set rc=%errorlevel%",
        f'echo robocopy of the new files exit code %rc% >> "{log}"',
        "if %rc% GEQ 8 goto rollback",
        "goto loose",
        ":movefailed",
        f'echo Could not move the old files: something still has them open. Programs running from the EV AI folder: >> "{log}"',
        f"{holders_list} >> \"{log}\" 2>&1",
        "goto failed",
        ":moved",
        f'echo Old folder moved aside after %t% retries >> "{log}"',
        f'move "{new_internal}" "{internal}" >> "{log}" 2>&1 || goto rollback',
        ":loose",
        # the few loose files next to it (EV_AI.exe ...): top folder only, _internal excluded
        f'robocopy "{new_dir}" "{app_root}" /XD _internal /R:30 /W:2 /NFL /NDL /NJH /NJS >> "{log}" 2>&1',
        "set rc=%errorlevel%",
        f'echo robocopy exit code %rc% (0-7 is success, 8 or more is a failure) >> "{log}"',
        "if %rc% GEQ 8 goto rollback",
        f'echo UPDATE OK >> "{log}"',
        f'start "" /b cmd /c rd /s /q "{internal_old}"',
        f'if exist "{app_root}\\EV_AI.exe.old" start "" /b cmd /c del /f /q "{app_root}\\EV_AI.exe.old"',
        f'rmdir /s /q "{stage}"',
        f'del "{busy}" >nul 2>&1',
        f'start "" "{exe}"',
        'del "%~f0"',
        "exit /b 0",
        ":rollback",
        f'echo Swap failed, putting the old version back >> "{log}"',
        'if "%mode%"=="files" goto rollbackfiles',
        f'if exist "{internal}" rd /s /q "{internal}" >> "{log}" 2>&1',
        f'if exist "{internal_old}" move "{internal_old}" "{internal}" >> "{log}" 2>&1',
        "goto failed",
        ":rollbackfiles",
        f'robocopy "{internal_old}" "{internal}" /E /IS /IT /R:3 /W:1 /MOVE /NFL /NDL /NJH /NJS >> "{log}" 2>&1',
        f'if exist "{app_root}\\EV_AI.exe.old" (del /f /q "{app_root}\\EV_AI.exe" >nul 2>&1 & ren "{app_root}\\EV_AI.exe.old" EV_AI.exe)',
        ":failed",
        f'echo UPDATE FAILED, starting the old version again >> "{log}"',
        f'del "{busy}" >nul 2>&1',
        f'start "" "{exe}"',
        "exit /b 1",
        ":killholders",
        f'echo Closing programs that still run from the EV AI folder >> "{log}"',
        f"{kill_holders} >> \"{log}\" 2>&1",
        "exit /b 0",
    ]
    text = "\r\n".join(lines) + "\r\n"
    try:
        script.write_text(text, encoding="mbcs")      # Windows' own code page, so cmd reads non-English paths
    except LookupError:
        script.write_text(text, encoding="utf-8")
    PENDING_SCRIPT = script
    return script


def cleanup_leftovers(app_root: Path) -> None:
    """Removes folders/files an earlier update left behind (best effort, never raises)."""
    import shutil
    try:
        for old in app_root.glob("_internal.old*"):
            shutil.rmtree(old, ignore_errors=True)
        (app_root / "EV_AI.exe.old").unlink(missing_ok=True)
    except Exception:
        pass


def update_in_progress(app_root: Path, max_age: float = 300.0) -> bool:
    """True while the update helper is still swapping files (it leaves data/update_busy.txt)."""
    import time
    try:
        busy = app_root / "data" / "update_busy.txt"
        return busy.exists() and (time.time() - busy.stat().st_mtime) < max_age
    except Exception:
        return False


def failed_update_notice(app_root: Path, running_version: str) -> str:
    """After a restart: if an update was staged but this is still the old version, say so
    and include the end of data/update_log.txt. Returns '' when everything is fine."""
    marker = app_root / "data" / "update_pending.json"
    if not marker.exists():
        return ""
    try:
        wanted = json.loads(marker.read_text(encoding="utf-8")).get("version", "")
    except Exception:
        wanted = ""
    marker.unlink(missing_ok=True)
    if not wanted or parse_version(running_version) >= parse_version(wanted):
        return ""
    try:
        tail = "\n".join((app_root / "data" / "update_log.txt").read_text(encoding="utf-8", errors="ignore")
                         .strip().splitlines()[-10:])
    except Exception:
        tail = "(no update log was written, the update helper may not have run)"
    return (f"The update to {wanted} did not install, you are still on {running_version}.\n\n"
            f"Update log:\n{tail}\n\nTry again after closing any File Explorer window that shows the EV AI folder "
            f"and pausing your antivirus for a minute. If it still fails, send this to the developer, or install by hand from the Releases page.")


def check_and_install(url: str, current_version: str, app_root: Path, progress=None) -> dict:
    """Whole flow in one call (used by the UI's worker thread after the
    user confirms): returns {"version", "files", "requirements_ok", "note"}."""
    info = fetch_info(url)
    if parse_version(info["version"]) <= parse_version(current_version):
        raise UpdateError(f"You're already up to date ({current_version}).")
    if not info["zip_url"]:
        raise UpdateError("This update has no download link, so it can't be installed automatically.")
    if is_frozen():
        zip_path = _download_big(info["zip_url"], info["sha256"], progress)
        try:
            stage_frozen(zip_path, app_root)
        finally:
            zip_path.unlink(missing_ok=True)
        try:
            (app_root / "data" / "update_pending.json").write_text(
                json.dumps({"version": info["version"], "from": current_version}), encoding="utf-8")
        except Exception:
            pass
        return {"version": info["version"], "files": 0, "requirements_ok": True,
                "note": "", "backup": "", "frozen": True}
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
