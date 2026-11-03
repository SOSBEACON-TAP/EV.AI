"""
core/vpn.py
-----------
Connect / disconnect a VPN you ALREADY have, by name. EV AI does not provide a VPN service.
  * "windows"  : a VPN added in Windows Settings > Network > VPN (controlled with rasdial; no admin rights).
  * "openvpn"  : OpenVPN GUI with a profile of that name (openvpn-gui --command connect <name>).
"""

import os
import subprocess

from core import user_prefs

_NOWINDOW = 0x08000000 if os.name == "nt" else 0


def _run(cmd: list[str], timeout: float = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NOWINDOW)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except FileNotFoundError:
        return 127, "not found"
    except Exception as e:
        return 1, str(e)


def _kind() -> str:
    return user_prefs.get("vpn_kind") or "windows"


def _name() -> str:
    return (user_prefs.get("vpn_name") or "").strip()


def _openvpn_gui() -> str:
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        p = os.path.join(base, "OpenVPN", "bin", "openvpn-gui.exe")
        if os.path.exists(p):
            return p
    return "openvpn-gui.exe"


def is_configured() -> bool:
    return bool(_name())


def connect() -> tuple[bool, str]:
    name = _name()
    if not name:
        return False, "No VPN is set up yet. Open Settings, VPN and type the name of your VPN."
    if _kind() == "openvpn":
        code, out = _run([_openvpn_gui(), "--command", "connect", name], 20)
        return (code == 0), (f"Asked OpenVPN to connect {name}." if code == 0 else f"OpenVPN GUI problem: {out}")
    code, out = _run(["rasdial", name])
    return (code == 0), (f"Connected to {name}." if code == 0 else f"Couldn't connect to {name}: {out.splitlines()[-1] if out else code}")


def disconnect() -> tuple[bool, str]:
    name = _name()
    if not name:
        return False, "No VPN is set up yet."
    if _kind() == "openvpn":
        code, out = _run([_openvpn_gui(), "--command", "disconnect", name], 20)
        return (code == 0), (f"Asked OpenVPN to disconnect {name}." if code == 0 else f"OpenVPN GUI problem: {out}")
    code, out = _run(["rasdial", name, "/disconnect"])
    return (code == 0), (f"Disconnected {name}." if code == 0 else f"Couldn't disconnect: {out.splitlines()[-1] if out else code}")


def status() -> str:
    name = _name()
    if not name:
        return "No VPN is set up yet."
    if _kind() == "openvpn":
        try:
            import psutil
            up = any((p.info["name"] or "").lower() == "openvpn.exe" for p in psutil.process_iter(["name"]))
        except Exception:
            up = False
        return "OpenVPN is running." if up else "OpenVPN is not connected."
    code, out = _run(["rasdial"], 15)
    return f"{name} is connected." if name.lower() in out.lower() else f"{name} is not connected."
