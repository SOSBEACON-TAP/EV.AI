"""
core/antivirus.py
-----------------
Antivirus scans through Microsoft Defender, the antivirus built into Windows. EV AI does not contain its
own scanning engine: it starts Defender's scans, updates its definitions and lists what it found.
If another antivirus has replaced Defender, Windows switches Defender off and these will say so.
"""

from __future__ import annotations

import os
import re
import subprocess

_NOWIN = 0x08000000 if os.name == "nt" else 0


def _ps(script: str, timeout: float) -> tuple[int, str]:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                           capture_output=True, text=True, timeout=timeout, creationflags=_NOWIN)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except FileNotFoundError:
        return 127, "PowerShell not found (Windows only)."
    except subprocess.TimeoutExpired:
        return 124, "The scan is still running in the background (Windows Security keeps going)."
    except Exception as e:
        return 1, str(e)


def _clean(out: str) -> str:
    return re.sub(r"\s+\n", "\n", out).strip()


def update_definitions() -> tuple[bool, str]:
    code, out = _ps("Update-MpSignature", 300)
    return code == 0, "Virus definitions are up to date." if code == 0 else f"Couldn't update: {_clean(out)[:300]}"


def scan(kind: str = "quick", path: str = "") -> tuple[bool, str]:
    """kind: quick | full | custom (path = file or folder). Blocks until the scan ends (the caller runs it in a thread)."""
    if kind == "custom":
        if not path:
            return False, "Choose a file or folder first."
        safe = path.replace("'", "''")
        code, out = _ps(f"Start-MpScan -ScanType CustomScan -ScanPath '{safe}'", 3600)
    elif kind == "full":
        code, out = _ps("Start-MpScan -ScanType FullScan", 4 * 3600)
    else:
        code, out = _ps("Start-MpScan -ScanType QuickScan", 1800)
    if code != 0:
        return False, f"Scan problem: {_clean(out)[:300] or 'Defender may be turned off or replaced by another antivirus.'}"
    return True, "Scan finished."


def threats() -> list[dict]:
    """Threats Defender has found: [{name, severity, status, resources}]."""
    code, out = _ps("Get-MpThreatDetection | Select-Object -First 15 ThreatID,InitialDetectionTime,Resources | ConvertTo-Json -Compress; "
                    "'---'; Get-MpThreat | Select-Object -First 15 ThreatID,ThreatName,SeverityID,IsActive | ConvertTo-Json -Compress", 60)
    import json
    found = []
    if code != 0 or "---" not in out:
        return found
    det, _, thr = out.partition("---")

    def load(text):
        text = text.strip()
        if not text:
            return []
        try:
            v = json.loads(text)
            return v if isinstance(v, list) else [v]
        except ValueError:
            return []
    where = {d.get("ThreatID"): ", ".join(d.get("Resources") or []) for d in load(det)}
    sev = {1: "low", 2: "moderate", 4: "high", 5: "severe"}
    for t in load(thr):
        found.append({"name": t.get("ThreatName", "?"), "severity": sev.get(t.get("SeverityID"), "unknown"),
                      "status": "ACTIVE" if t.get("IsActive") else "handled", "resources": where.get(t.get("ThreatID"), "")[:160]})
    return found
