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

FRIDAY_QSS = _recolor(("#FF4FA3", "#FFA3D1", "#FF7FBD", "#A8497A", "#F8D8E8", "#14060E", "#0E030A", "#080106",
                       "rgba(255, 79, 163,", "rgba(255,79,163,", "rgba(20, 6, 14,", "rgba(22, 6, 16,", "rgba(10, 2, 6,"))
TARS_QSS = _recolor(("#C9D1D9", "#FFFFFF", "#E6EDF3", "#6B7580", "#EEF2F6", "#0D1014", "#080A0D", "#040506",
                     "rgba(201, 209, 217,", "rgba(201,209,217,", "rgba(13, 16, 20,", "rgba(14, 17, 22,", "rgba(6, 8, 10,"))
GIDEON_QSS = _recolor(("#19E3D0", "#8FFFF3", "#4DF0E0", "#2F8F88", "#D2F7F3", "#041413", "#020C0B", "#010606",
                       "rgba(25, 227, 208,", "rgba(25,227,208,", "rgba(4, 20, 19,", "rgba(3, 22, 20,", "rgba(0, 10, 9,"))
EDITH_QSS = _recolor(("#4DA3FF", "#BFDDFF", "#7FBFFF", "#3F6A99", "#DCEBFA", "#060E16", "#030A10", "#010406",
                      "rgba(77, 163, 255,", "rgba(77,163,255,", "rgba(6, 14, 20,", "rgba(6, 16, 24,", "rgba(2, 8, 12,"))
