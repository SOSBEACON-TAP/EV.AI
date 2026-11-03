"""Stylesheet for Ultron mode: the Jarvis console layout in cold red and black."""

from ui.jarvis_style import JARVIS_QSS

_SWAPS = (
    ("#FFC400", "#FF2A2A"), ("#FFE066", "#FF8080"), ("#FFD84D", "#FF6666"), ("#B89A3C", "#A04040"),
    ("#F2E4B8", "#F0D0D0"), ("#120D02", "#140204"), ("#0B0801", "#0C0102"), ("#060400", "#060001"),
    ("rgba(255, 196, 0,", "rgba(255, 42, 42,"), ("rgba(255,196,0,", "rgba(255,42,42,"),
    ("rgba(18, 12, 2,", "rgba(20, 2, 4,"), ("rgba(20, 14, 2,", "rgba(22, 2, 4,"), ("rgba(8, 5, 0,", "rgba(10, 0, 2,"),
)


def _build() -> str:
    text = JARVIS_QSS
    for old, new in _SWAPS:
        text = text.replace(old, new)
    return text


ULTRON_QSS = _build()
