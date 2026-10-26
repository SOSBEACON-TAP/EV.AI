# PyInstaller spec for EV AI. Put this file next to main.py.
# Build:  pyinstaller EV_AI.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

datas = [
    ("assets", "assets"),
    ("ui/styles", "ui/styles"),
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
hidden += ["pyttsx3.drivers", "pyttsx3.drivers.sapi5", "comtypes", "comtypes.client", "win32com.client"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib.tests", "scipy.tests"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="EV_AI",
    icon="assets/icons/ev.ico",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="EV_AI")
