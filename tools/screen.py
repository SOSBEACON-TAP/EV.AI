"""
tools/screen.py
-----------------
Jarvis Pro: read what's on the screen.

Captures the primary display (or the active window when possible) and
extracts text via OCR so EV can answer "what's on my screen", "read that
error", "summarise this window", etc.

OCR backends (tried in order):
  1. pytesseract  (optional package + Tesseract installed on the PC)
  2. Windows.Media.Ocr via PowerShell (Windows 10/11, no extra packages)

If neither works, a screenshot is still saved under data/screenshots/ and
the path is returned so the vision/image path can be used instead.
"""

from __future__ import annotations

import datetime
import io
import subprocess
import sys
from pathlib import Path

from config import APP_ROOT

_MAX_OCR_CHARS = 12000
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _screenshots_dir() -> Path:
    d = Path(APP_ROOT) / "data" / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _capture_png_bytes(region: str = "screen") -> bytes:
    """Return PNG bytes of the primary screen or active window."""
    # Prefer mss (fast, multi-monitor aware); fall back to pyautogui/Pillow.
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            # monitor 1 = primary; 0 = all monitors virtual
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(mon)
            return mss.tools.to_png(shot.rgb, shot.size)
    except Exception:
        pass

    try:
        import pyautogui

        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        raise RuntimeError(f"Could not capture screen: {e}") from e


def _ocr_pytesseract(png_bytes: bytes) -> str | None:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(png_bytes))
        text = pytesseract.image_to_string(img) or ""
        return text.strip() or None
    except Exception:
        return None


def _ocr_windows_powershell(png_path: Path) -> str | None:
    """Use Windows.Media.Ocr (built into Win10/11) via a short PowerShell script."""
    if sys.platform != "win32":
        return None
    # PowerShell OCR using Windows Runtime. Works offline once the language pack is present.
    ps = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Media.Ocr,ContentType=WindowsRuntime]

function Await($WinRtTask, $ResultType) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod })[0]
    $asTask = $asTask.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$path = $args[0]
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language 'en-US')) }
if (-not $engine) { Write-Output ''; exit 0 }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
Write-Output $result.Text
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps, str(png_path)],
            capture_output=True,
            timeout=45,
            creationflags=_NO_WINDOW,
        )
        text = proc.stdout.decode("utf-8", errors="replace").strip()
        return text or None
    except Exception:
        return None


def read_screen(region: str = "screen") -> dict:
    """Capture the screen and return OCR text (and a saved screenshot path).

    region: 'screen' (primary monitor) — reserved for future 'window' / 'region'.
    """
    try:
        png = _capture_png_bytes(region)
    except Exception as e:
        return {"error": str(e)}

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _screenshots_dir() / f"screen_{stamp}.png"
    try:
        path.write_bytes(png)
    except OSError as e:
        return {"error": f"Could not save screenshot: {e}"}

    _prune()
    text = _ocr_pytesseract(png)
    engine = "pytesseract" if text else None
    if not text:
        text = _ocr_windows_powershell(path)
        engine = "windows_ocr" if text else None

    if text and len(text) > _MAX_OCR_CHARS:
        text = text[:_MAX_OCR_CHARS]
        truncated = True
    else:
        truncated = False

    result = {
        "screenshot_path": str(path),
        "ocr_engine": engine or "none",
        "characters": len(text or ""),
        "truncated": truncated,
    }
    if text:
        result["text"] = text
        result["status"] = "ok"
    else:
        result["status"] = "screenshot_only"
        result["message"] = (
            "Screenshot saved but no OCR engine was available. "
            "Install Tesseract + pytesseract, or use Windows 10/11 with the English OCR language pack. "
            "You can still open the image path or ask the user to describe what they see."
        )
    return result


def _prune(keep: int = 20) -> None:
    """Keep only the newest screenshots so they don't pile up on disk."""
    try:
        files = sorted(_screenshots_dir().glob("screen_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[keep:]:
            p.unlink(missing_ok=True)
    except OSError:
        pass


def list_recent_screenshots(limit: int = 5) -> dict:
    """List the most recent screenshots EV has taken."""
    d = _screenshots_dir()
    files = sorted(d.glob("screen_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for p in files[: max(1, min(limit, 20))]:
        items.append({
            "path": str(p),
            "modified": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
            "size_kb": round(p.stat().st_size / 1024, 1),
        })
    return {"screenshots": items, "count": len(items)}



def get_active_window_title() -> dict:
    """Return the title of the foreground window (Windows)."""
    if sys.platform != "win32":
        return {"error": "Only available on Windows."}
    script = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Win {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
}
"@
$hwnd = [Win]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 512
[void][Win]::GetWindowText($hwnd, $sb, $sb.Capacity)
$sb.ToString()
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            timeout=8,
            creationflags=_NO_WINDOW,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        title = (proc.stdout or "").strip()
        return {"title": title or "(no title)", "ok": True}
    except Exception as e:
        return {"error": str(e)}
