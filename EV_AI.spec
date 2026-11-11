# PyInstaller spec for EV AI. Put this file next to main.py.
# Build:  pyinstaller EV_AI.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

datas = [
    ("assets", "assets"),
    ("ui/styles", "ui/styles"),
    ("chrome_extension", "chrome_extension"),
]
binaries = []
hidden = []
for pkg in ("core", "tools", "ui", "voice", "database"):
    hidden += collect_submodules(pkg)
for pkg in ("mediapipe", "speech_recognition", "pyttsx3", "edge_tts", "pycaw"):
    try:
        datas += collect_data_files(pkg)
        hidden += collect_submodules(pkg)
    except Exception:
        pass
try:
    binaries += collect_dynamic_libs("mediapipe")
except Exception:
    pass
# offline speech models (~40 MB) are not used; only the online recogniser is
datas = [d for d in datas if "pocketsphinx" not in d[0].lower() and "pocketsphinx" not in d[1].lower()]
hidden += ["scripts.create_shortcut", "core.shortcuts"]
# the standard-library modules that code written by Ultron's RUN CODE commonly imports (the app must carry them)
hidden += ["random", "math", "statistics", "datetime", "json", "csv", "re", "itertools", "collections", "string", "time",
           "os", "sys", "pathlib", "shutil", "hashlib", "base64", "textwrap", "fractions", "decimal", "heapq", "bisect",
           "functools", "operator", "glob", "fnmatch", "zipfile", "tempfile", "uuid", "secrets", "socket", "threading",
           "subprocess", "sqlite3", "calendar", "html", "xml.etree.ElementTree", "difflib", "pprint", "copy", "typing",
           "dataclasses", "enum", "abc", "io", "struct", "platform", "getpass", "argparse", "logging", "webbrowser",
           "http.server", "http.client", "urllib.request", "urllib.parse", "queue", "asyncio", "ipaddress", "shlex",
           "stat", "gzip", "tarfile", "pickle", "timeit", "traceback", "unicodedata", "locale", "ctypes", "winreg"]
hidden += ["pyttsx3.drivers", "pyttsx3.drivers.sapi5", "comtypes", "comtypes.client", "win32com.client"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    # EV AI only uses QtCore/QtWidgets/QtGui/QtMultimedia: leave out the rest of Qt
    # (WebEngine alone is >150 MB) to keep the download small.
    excludes=["tkinter", "matplotlib.tests", "scipy.tests", "jax", "jaxlib", "scipy", "ml_dtypes", "opt_einsum"] + [
        "PySide6." + m for m in (
            "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel", "QtWebSockets",
            "QtPdf", "QtPdfWidgets", "QtQml", "QtQuick", "QtQuickWidgets", "QtQuick3D", "QtQuickControls2",
            "Qt3DCore", "Qt3DRender", "Qt3DInput", "Qt3DLogic", "Qt3DAnimation", "Qt3DExtras",
            "QtCharts", "QtDataVisualization", "QtGraphs", "QtSql", "QtTest", "QtBluetooth", "QtNfc",
            "QtSensors", "QtSerialPort", "QtPositioning", "QtLocation", "QtRemoteObjects", "QtScxml",
            "QtStateMachine", "QtTextToSpeech", "QtVirtualKeyboard", "QtDesigner", "QtHelp", "QtUiTools",
            "QtOpenGL", "QtOpenGLWidgets", "QtSvg", "QtSvgWidgets", "QtHttpServer", "QtNetworkAuth",
        )
    ],
)
pyz = PYZ(a.pure)
# File details shown in Properties > Details of EV_AI.exe (publisher name there is ours;
# the SmartScreen "Publisher" line needs a paid code-signing certificate instead).
_vfile = None
try:
    import os, sys as _sys
    _sys.path.insert(0, SPECPATH)
    from app_version import VERSION as _V
    from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo,
                                                      StringTable, StringStruct, VarFileInfo, VarStruct)
    _t = tuple(int(x) for x in (_V.split(".") + ["0", "0", "0"])[:3]) + (0,)
    _info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=_t, prodvers=_t, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Shri Nikil Prakash V"),
            StringStruct("FileDescription", "EV AI Assistant"),
            StringStruct("FileVersion", _V),
            StringStruct("InternalName", "EV_AI"),
            StringStruct("LegalCopyright", "Copyright (c) Shri Nikil Prakash V"),
            StringStruct("OriginalFilename", "EV_AI.exe"),
            StringStruct("ProductName", "EV AI"),
            StringStruct("ProductVersion", _V)])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])])])
    _vfile = os.path.join(SPECPATH, "build_version_info.txt")
    open(_vfile, "w", encoding="utf-8").write(str(_info))
except Exception as _e:   # never let the version details break the build
    print("version info skipped:", _e)
    _vfile = None

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="EV_AI",
    icon="assets/icons/ev.ico",
    version=_vfile,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="EV_AI")
