"""
ui/theme.py
-------------
Loads the app-wide stylesheet for the chosen theme (dark, light or one of the
colour themes below, saved in core/user_prefs.py) and applies it live — Settings switches
theme without a restart by calling apply_theme() again.

The HUD overlay and startup screen paint their own dark glass and are
intentionally the same in both themes (they float over other apps / sit
before the main window exists). Dialogs opened from Settings get their
colors from dialog_stylesheet() so they match the chosen theme.
"""

import re
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

_STYLES_DIR = Path(__file__).resolve().parent / "styles"

# id -> (label, a1 "left/status" accent, a2 "right/action" accent, highlight, (bg centre, bg mid, bg edge))
# Everything except "light" is built from dark_theme.qss with these colours swapped in.
_THEME_DEFS = {
    "dark":     ("Dark (red + blue)",  (240, 70, 90),   (60, 140, 240),  "#5FD0E8", ("#10131E", "#0A0C15", "#05060A")),
    "crimson":  ("Crimson",            (255, 70, 60),   (255, 150, 60),  "#FFB070", ("#1C0F10", "#120A0B", "#080405")),
    "emerald":  ("Emerald",            (40, 220, 150),  (40, 170, 210),  "#5FF0B8", ("#0C1A16", "#08120F", "#040907")),
    "violet":   ("Violet neon",        (200, 80, 255),  (255, 80, 180),  "#D8A0FF", ("#150E20", "#0E0916", "#07040B")),
    "ocean":    ("Ocean",              (60, 190, 255),  (70, 110, 255),  "#7FD8FF", ("#0A1622", "#07101A", "#03080D")),
    "gold":     ("Gold",               (255, 190, 60),  (230, 130, 40),  "#FFD27A", ("#1A140A", "#110D07", "#080603")),
    "sunset":   ("Sunset",             (255, 110, 70),  (255, 70, 150),  "#FFA68A", ("#1E1010", "#140A0C", "#090406")),
    "midnight": ("Midnight indigo",    (120, 110, 255), (70, 150, 255),  "#A9B4FF", ("#0D0E22", "#080918", "#04040C")),
    "mono":     ("Mono (grey)",        (200, 200, 205), (150, 160, 175), "#E6E9EE", ("#151618", "#0E0F11", "#070708")),
    "light":    ("Normal (light)",     (230, 60, 80),   (60, 140, 240),  "#2C6FA8", ("#F2F6FA", "#F2F6FA", "#F2F6FA")),
}

THEME_CHOICES = [(tid, d[0]) for tid, d in _THEME_DEFS.items()] + [("custom", "Custom (your colours)")]
_current = "dark"


def _hex_rgb(text: str, fallback: tuple) -> tuple:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (text or "").strip())
    if not m:
        return fallback
    v = m.group(1)
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def _darken(rgb, factor):
    return "#%02X%02X%02X" % tuple(int(c * factor) for c in rgb)


def _def(theme: str):
    """The (label, a1, a2, highlight, (bg0, bg1, bg2)) tuple for a theme; the
    "custom" theme is built from the colours saved in Personalization."""
    if theme == "custom":
        from core import user_prefs
        prefs = user_prefs.load()
        a1 = _hex_rgb(prefs["custom_accent1"], (240, 70, 90))
        a2 = _hex_rgb(prefs["custom_accent2"], (60, 140, 240))
        bg = _hex_rgb(prefs["custom_bg"], (16, 19, 30))
        bg0 = "#%02X%02X%02X" % bg
        return ("Custom (your colours)", a1, a2, _lighten(a2, 0.45), (bg0, _darken(bg, 0.65), _darken(bg, 0.4)))
    return _THEME_DEFS[theme]


def font_scale() -> float:
    try:
        from core import user_prefs
        return max(0.8, min(1.6, int(user_prefs.get("font_scale")) / 100.0))
    except Exception:
        return 1.0


def _scale_fonts(qss: str) -> str:
    """Multiply every `font-size: Npx` in a stylesheet by the chosen text size."""
    k = font_scale()
    if abs(k - 1.0) < 0.01:
        return qss
    return re.sub(r"font-size:\s*(\d+(?:\.\d+)?)px",
                  lambda m: f"font-size: {max(7, round(float(m.group(1)) * k))}px", qss)


def normalize(theme: str) -> str:
    return theme if theme in _THEME_DEFS or theme == "custom" else "dark"


def current() -> str:
    return _current


def core_colors(theme: str | None = None):
    """(left accent, right accent) QColors — the AI core and video HUD use these."""
    d = _def(normalize(theme or _current))
    return QColor(*d[1]), QColor(*d[2])


def highlight(theme: str | None = None) -> QColor:
    return QColor(_def(normalize(theme or _current))[3])


def _rgba(rgb, alpha):
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"


def _lighten(rgb, amount=0.55):
    return "#%02X%02X%02X" % tuple(int(c + (255 - c) * amount) for c in rgb)


def _build_qss(theme: str) -> str:
    base = (_STYLES_DIR / "dark_theme.qss").read_text(encoding="utf-8")
    if theme == "dark":
        return base
    _label, a1, a2, hl, (bg0, bg1, bg2) = _def(theme)
    swaps = [
        ("#10131E", bg0), ("#0A0C15", bg1), ("#05060A", bg2),
        ("rgba(240, 70, 90, 70)", _rgba(a1, 80)),
        ("rgba(60, 140, 240, 70)", _rgba(a2, 80)),
        ("#5FD0E8", hl),
        ("rgba(90, 160, 230, 90)", _rgba(a2, 100)),
        ("rgba(90, 130, 200, 30)", _rgba(a2, 32)),
        ("rgba(90, 150, 220, 90)", _rgba(a2, 100)),
        ("rgba(90, 150, 220, 70)", _rgba(a2, 80)),
        ("rgba(90, 150, 220, 110)", _rgba(a2, 125)),
        ("#C6DCF4", _lighten(a2, 0.7)),
        ("rgba(230, 70, 90, 90)", _rgba(a1, 100)),
        ("rgba(240, 90, 110, 140)", _rgba(a1, 150)),
        ("#F0576E", _lighten(a1, 0.1)),
        ("rgba(120, 150, 200, 90)", _rgba(a2, 100)),
    ]
    for old, new in swaps:
        base = base.replace(old, new)
    return base


def apply_theme(app: QApplication, theme: str) -> None:
    global _current
    name = normalize(theme)
    _current = name
    try:
        if name == "light":
            qss = (_STYLES_DIR / "light_theme.qss").read_text(encoding="utf-8")
        else:
            qss = _build_qss(name)
        app.setStyleSheet(_scale_fonts(qss))
        base = app.font()
        base.setPointSizeF(round(9.0 * font_scale(), 1))
        app.setFont(base)
    except FileNotFoundError:
        # UI still works with default Qt styling if the stylesheet is missing.
        print(f"[EV AI] Warning: stylesheet for '{name}' not found in {_STYLES_DIR}, using defaults.")


def dialog_stylesheet(theme: str) -> str:
    theme = normalize(theme)
    if theme == "light":
        bg, text, sub, accent = "#F2F6FA", "#1B2A3A", "#2C6FA8", "#4A6078"
        btn_bg, btn_text, btn_border, btn_hover = (
            "rgba(40,110,215,28)", "#1B3F6B", "rgba(40,110,215,120)", "rgba(40,110,215,75)",
        )
        field_bg, field_text, field_border = "#FFFFFF", "#10253A", "rgba(40,110,215,130)"
    else:
        _label, _a1, a2, hl, (bg0, _bg1, _bg2) = _def(theme)
        bg, text, sub, accent = bg0, "#d8eeff", _lighten(a2, 0.45), _lighten(a2, 0.25)
        btn_bg, btn_text = _rgba(a2, 32), _lighten(a2, 0.7)
        btn_border, btn_hover = _rgba(a2, 100), _rgba(a2, 80)
        field_bg, field_text, field_border = "rgba(10,14,22,220)", "white", _rgba(a2, 110)
    return _scale_fonts(
        f"QDialog {{ background: {bg}; }} "
        f"QLabel {{ color: {text}; font-size: 12px; }} "
        f"QLabel[role=\"sub\"] {{ color: {sub}; font-size: 11px; }} "
        f"QLabel[role=\"section\"] {{ color: {accent}; font-size: 10px; font-weight: 600; letter-spacing: 1px; }} "
        f"QCheckBox {{ color: {text}; font-size: 12px; spacing: 8px; }} "
        f"QComboBox {{ background: {field_bg}; color: {field_text}; border: 1px solid {field_border}; "
        f"border-radius: 6px; padding: 4px 8px; }} "
        f"QComboBox QAbstractItemView {{ background: {field_bg}; color: {field_text}; }} "
        f"QPushButton {{ background: {btn_bg}; color: {btn_text}; border: 1px solid {btn_border}; "
        f"border-radius: 6px; padding: 6px 10px; font-size: 11px; }} "
        f"QPushButton:hover {{ background: {btn_hover}; }} "
        f"QLineEdit {{ background: {field_bg}; color: {field_text}; border: 1px solid {field_border}; "
        f"border-radius: 6px; padding: 5px 7px; }}"
    )
