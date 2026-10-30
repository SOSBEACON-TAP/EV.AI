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
# offline speech models (~40 MB) are not used; only the online recogniser is
datas = [d for d in datas if "pocketsphinx" not in d[0].lower() and "pocketsphinx" not in d[1].lower()]
hidden += ["scripts.create_shortcut", "core.shortcuts"]
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
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="EV_AI",
    icon="assets/icons/ev.ico",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="EV_AI")
