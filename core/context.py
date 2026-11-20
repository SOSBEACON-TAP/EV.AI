"""
core/context.py
-----------------
Context awareness: a guess at what you are doing from the program in front and its window title, plus one short,
relevant offer of help. It reads ONLY the program name and window title on this PC: no screenshot, no AI call,
nothing leaves the computer. It is off until you turn it on.
"""
from __future__ import annotations

CATEGORIES = [
    ("coding", ("code", "devenv", "pycharm", "idea", "sublime", "notepad++", "windowsterminal", "cmd", "powershell", "wt"),
     "You are coding. Want me to explain an error, open the docs, or start a 25-minute focus session?"),
    ("docs", ("winword", "excel", "powerpnt", "acrord32", "acrobat", "onenote", "notepad", "wordpad", "soffice"),
     "You are in a document. I can summarize it, fix the wording, or turn your notes into a to-do list."),
    ("game", ("steam", "epicgameslauncher", "valorant", "fortniteclient", "minecraft", "robloxplayerbeta", "gta5", "javaw"),
     "Game on. Want a break reminder every 45 minutes, or notifications silenced?"),
    ("chat", ("whatsapp", "discord", "telegram", "teams", "slack", "skype"),
     "You are chatting. I can draft a reply or read your unread messages out loud."),
    ("design", ("photoshop", "illustrator", "figma", "canva", "gimp", "krita", "blender"),
     "Creative work. I can describe an image, suggest a colour palette, or set a focus timer."),
    ("video", ("vlc", "wmplayer", "spotify", "netflix", "mpc-hc", "potplayer"),
     "Relaxing? I can set a sleep timer or pause everything when you get a message."),
]
_BROWSER = ("chrome", "msedge", "firefox", "brave", "opera", "vivaldi")
_WEB_HINTS = (("youtube", "video", "Watching something? I can set a timer so you do not lose the evening."),
              ("github", "coding", "You are on GitHub. I can explain code or summarize this page."),
              ("docs.google", "docs", "You are in a document. I can summarize it, fix the wording, or turn notes into to-dos."),
              ("stack overflow", "coding", "Stuck on a problem? Paste the error and I will explain it."),
              ("wikipedia", "research", "Researching? I can summarize this page or collect the key points."),
              ("scholar", "research", "Researching? I can summarize this page or collect the key points."))


def classify(program: str, title: str) -> tuple[str, str]:
    """(category, offer) for the program in front. ('', '') when there is nothing useful to say."""
    prog = (program or "").lower()
    prog = prog[:-4] if prog.endswith(".exe") else prog
    low_title = (title or "").lower()
    if prog in _BROWSER:
        for hint, cat, offer in _WEB_HINTS:
            if hint in low_title:
                return cat, offer
        return "browsing", ""
    for cat, progs, offer in CATEGORIES:
        if prog in progs:
            return cat, offer
    return "", ""


class ContextTracker:
    """Call tick() every few seconds. Returns an offer only when the activity has been steady for a while and has
    changed since the last offer, and never more than one offer every few minutes."""

    def __init__(self, steady_ticks: int = 4, cooldown_s: float = 300.0):
        self._steady_need = steady_ticks
        self._cool = cooldown_s
        self._cat = ""
        self._count = 0
        self._last_offered = ""
        self._last_time = 0.0

    def tick(self, program: str, title: str, now: float) -> str:
        cat, offer = classify(program, title)
        if cat != self._cat:
            self._cat, self._count = cat, 0
        self._count += 1
        if (cat and offer and self._count == self._steady_need and cat != self._last_offered
                and now - self._last_time >= self._cool):
            self._last_offered, self._last_time = cat, now
            return offer
        return ""
