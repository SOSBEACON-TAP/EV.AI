"""Stylesheets for Game mode (green) and Karen mode (violet): the Jarvis console layout recoloured."""

from ui.jarvis_style import JARVIS_QSS

_OLD = ("#FFC400", "#FFE066", "#FFD84D", "#B89A3C", "#F2E4B8", "#120D02", "#0B0801", "#060400",
        "rgba(255, 196, 0,", "rgba(255,196,0,", "rgba(18, 12, 2,", "rgba(20, 14, 2,", "rgba(8, 5, 0,")


def _recolor(new: tuple) -> str:
    text = JARVIS_QSS
    for old, repl in zip(_OLD, new):
        text = text.replace(old, repl)
    return text


GAME_QSS = _recolor(("#2BFF88", "#9DFFC8", "#5CFFA3", "#3C8A5E", "#D0F0DC", "#04140C", "#020C06", "#010603",
                     "rgba(43, 255, 136,", "rgba(43,255,136,", "rgba(4, 20, 12,", "rgba(3, 22, 12,", "rgba(0, 10, 4,"))
KAREN_QSS = _recolor(("#B26BFF", "#D9B3FF", "#C58CFF", "#7A4DB0", "#E8D8F8", "#0E0614", "#080310", "#040108",
                      "rgba(178, 107, 255,", "rgba(178,107,255,", "rgba(14, 6, 20,", "rgba(16, 6, 22,", "rgba(6, 2, 10,"))
