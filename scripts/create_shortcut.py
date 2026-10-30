"""
scripts/create_shortcut.py
----------------------------
Creates an "EV" shortcut (with the EV icon) in the app folder and the Start
menu, so EV can be pinned to the taskbar: right-click the shortcut (or find
"EV" in the Start menu) -> Show more options -> Pin to taskbar.

The shortcut launches the app silently with the venv's pythonw.exe and is
stamped with the same taskbar identity (AppUserModelID) that main.py sets,
so the pinned icon and the running window are one button with the EV logo
instead of the Python one. Windows only.
"""

import base64
import os
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
APP_USER_MODEL_ID = "EV.AI.Assistant"   # must match main.py

_PS = r'''
$ErrorActionPreference = "Stop"
$target = __TARGET__; $args_ = __ARGS__; $work = __WORK__
$icon = __ICON__; $paths = @(__PATHS__); $aumid = __AUMID__

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class LnkId {
  [StructLayout(LayoutKind.Sequential, Pack = 4)] struct PropertyKey { public Guid fmtid; public uint pid; }
  [StructLayout(LayoutKind.Sequential)] struct PropVariant { public ushort vt; public ushort r1, r2, r3; public IntPtr p; public IntPtr p2; }
  [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPropertyStore {
    [PreserveSig] int GetCount(out uint c);
    [PreserveSig] int GetAt(uint i, out PropertyKey k);
    [PreserveSig] int GetValue(ref PropertyKey k, out PropVariant v);
    [PreserveSig] int SetValue(ref PropertyKey k, ref PropVariant v);
    [PreserveSig] int Commit();
  }
  [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPersistFile {
    void GetClassID(out Guid g);
    [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint mode);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string f, bool remember);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f);
    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string f);
  }
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class ShellLink {}
  public static void SetId(string lnk, string id) {
    object o = new ShellLink();
    ((IPersistFile)o).Load(lnk, 2);
    var store = (IPropertyStore)o;
    var key = new PropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
    var v = new PropVariant { vt = 31, p = Marshal.StringToCoTaskMemUni(id) };
    store.SetValue(ref key, ref v);
    store.Commit();
    ((IPersistFile)o).Save(lnk, true);
  }
}
"@

$ws = New-Object -ComObject WScript.Shell
foreach ($path in $paths) {
  $lnk = $ws.CreateShortcut($path)
  $lnk.TargetPath = $target
  $lnk.Arguments = $args_
  $lnk.WorkingDirectory = $work
  $lnk.IconLocation = $icon
  $lnk.Description = "EV - your AI assistant"
  $lnk.Save()
  try { [LnkId]::SetId($path, $aumid) } catch { Write-Output ("note: could not set taskbar id: " + $_.Exception.Message) }
  Write-Output ("created " + $path)
}
'''


def _q(value) -> str:
    """PowerShell single-quoted literal (only ' needs escaping)."""
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcuts(target, args: str, work, icon, paths) -> tuple[int, str]:
    """Creates .lnk files at `paths` pointing at `target`, stamped with EV's taskbar id.
    Returns (exit code, PowerShell output)."""
    script = (_PS
              .replace("__TARGET__", _q(target))
              .replace("__ARGS__", _q(args))
              .replace("__WORK__", _q(work))
              .replace("__ICON__", _q(icon))
              .replace("__PATHS__", ", ".join(_q(p) for p in paths))
              .replace("__AUMID__", _q(APP_USER_MODEL_ID)))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        capture_output=True, text=True, creationflags=0x08000000,  # no console flash
    )
    out = (result.stdout or "").strip()
    if result.returncode != 0:
        out += "\n" + (result.stderr or "").strip()
    return result.returncode, out


def main() -> int:
    if os.name != "nt":
        print("Shortcuts are Windows-only.")
        return 1

    venv_pythonw = APP_ROOT / "venv" / "Scripts" / "pythonw.exe"
    target = venv_pythonw if venv_pythonw.exists() else Path(sys.executable).with_name("pythonw.exe")
    icon = APP_ROOT / "assets" / "icons" / "ev.ico"
    start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    paths = [APP_ROOT / "EV.lnk"]
    if start_menu.is_dir():
        paths.append(start_menu / "EV.lnk")

    # inner quotes: the path may have spaces
    code, out = create_shortcuts(target, f'"{APP_ROOT / "main.py"}"', APP_ROOT, icon, paths)
    print(out)
    if code != 0:
        return code
    print("Done. Right-click 'EV' -> Show more options -> Pin to taskbar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
