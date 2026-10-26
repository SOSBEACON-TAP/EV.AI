"""
tools/clipboard.py
--------------------
Clipboard assistant tools: the AI can read what you copied (to summarize,
explain or rewrite it) and put a result back on the clipboard. Uses
PowerShell on Windows (no extra packages); pbpaste/pbcopy or xclip elsewhere.
Reading only happens when you ask ("summarize my clipboard"), never in the
background.
"""

import subprocess
import sys

_MAX_CHARS = 20000
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run(cmd: list, input_text: str | None = None, timeout: int = 8):
    return subprocess.run(
        cmd, input=input_text.encode("utf-8") if input_text is not None else None,
        capture_output=True, timeout=timeout, creationflags=_NO_WINDOW,
    )


def read_clipboard() -> dict:
    """Return the text currently on the clipboard."""
    try:
        if sys.platform == "win32":
            proc = _run(["powershell", "-NoProfile", "-Command",
                         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"])
        elif sys.platform == "darwin":
            proc = _run(["pbpaste"])
        else:
            proc = _run(["xclip", "-selection", "clipboard", "-o"])
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": f"Couldn't read the clipboard: {e}"}
    text = proc.stdout.decode("utf-8", errors="replace").strip("\r\n")
    if not text.strip():
        return {"error": "The clipboard is empty or doesn't hold text."}
    truncated = len(text) > _MAX_CHARS
    return {"text": text[:_MAX_CHARS], "characters": len(text), "truncated": truncated}


def write_clipboard(text: str) -> dict:
    """Put text on the clipboard (replaces what was there)."""
    if not (text or "").strip():
        return {"error": "Nothing to copy."}
    try:
        if sys.platform == "win32":
            proc = _run(["powershell", "-NoProfile", "-Command",
                         "[Console]::InputEncoding=[Text.Encoding]::UTF8; "
                         "$t=[Console]::In.ReadToEnd(); Set-Clipboard -Value $t"], input_text=text)
        elif sys.platform == "darwin":
            proc = _run(["pbcopy"], input_text=text)
        else:
            proc = _run(["xclip", "-selection", "clipboard"], input_text=text)
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": f"Couldn't write to the clipboard: {e}"}
    if proc.returncode != 0:
        return {"error": "The clipboard couldn't be updated."}
    return {"status": "copied", "characters": len(text)}
