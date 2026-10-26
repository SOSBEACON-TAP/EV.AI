"""
core/offline.py
-----------------
Offline mode: a small built-in command understander that handles the basics
WITHOUT the AI — open apps, timers and reminders, volume and media keys,
the time and date, simple maths, to-dos and notes. It uses the same tools
the AI would, so behaviour (and the action history) is identical.

Used in two ways:
  * as a fallback when the AI can't be reached (no internet, no API key,
    provider down) — then it answers whatever it understands and says so;
  * optionally first, before the AI (Settings -> "Handle simple commands
    without the AI"), which is faster and free for these everyday things.

handle() returns the reply text, or None if it doesn't understand — the
caller then carries on with the AI (or says the AI is unavailable).
"""

import ast
import operator
import re
from datetime import datetime

from core.router import ToolError

_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20,
                 "thirty": 30, "forty": 40, "sixty": 60, "half": 0.5}
_UNIT_SECONDS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600}
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def _safe_eval(expression: str) -> float:
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        raise ValueError("unsupported")
    return walk(ast.parse(expression, mode="eval"))


def _spoken_math(text: str) -> str:
    text = text.lower()
    for words, symbol in ((" plus ", "+"), (" minus ", "-"), (" times ", "*"), (" multiplied by ", "*"),
                          (" divided by ", "/"), (" over ", "/"), (" to the power of ", "**"),
                          (" mod ", "%"), ("×", "*"), ("÷", "/"), ("^", "**")):
        text = text.replace(words, symbol)
    return re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", text).replace(",", "")


def _duration_seconds(amount: str, unit: str) -> int | None:
    amount = amount.lower()
    value = float(amount) if re.fullmatch(r"\d+(\.\d+)?", amount) else _NUMBER_WORDS.get(amount)
    seconds = _UNIT_SECONDS.get(unit.lower().rstrip("s"))
    if value is None or seconds is None:
        return None
    return max(1, int(value * seconds))


def _nice(seconds: int) -> str:
    if seconds % 3600 == 0:
        n, unit = seconds // 3600, "hour"
    elif seconds % 60 == 0:
        n, unit = seconds // 60, "minute"
    else:
        n, unit = seconds, "second"
    return f"{n} {unit}{'' if n == 1 else 's'}"


class OfflineAssistant:
    def __init__(self, router):
        self._router = router

    # -- helpers ---------------------------------------------------------------
    def _run(self, tool: str, **arguments) -> dict:
        try:
            return self._router.execute(tool, arguments)
        except ToolError as e:
            return {"error": str(e)}

    # -- main entry -----------------------------------------------------------
    def handle(self, raw: str, fallback: bool = True) -> str | None:
        """fallback=True: AI is unavailable, so also try "open <anything>".
        fallback=False: AI will handle unknowns, so only answer what's certain."""
        if self._router is None:
            return None
        text = re.sub(r"^(hey |hi |ok |okay )?ev[,.:]?\s+", "", raw.strip(), flags=re.I)
        text = re.sub(r"\b(please|for me|can you|could you|would you)\b", "", text, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip(" .!?").strip()
        low = text.lower()
        if not low:
            return None

        for step in (self._time, self._volume_media, self._timer, self._todo_note, self._math):
            reply = step(low, text)
            if reply:
                return reply
        return self._open_app(low, fallback)

    # -- handlers -------------------------------------------------------------
    def _time(self, low: str, _text: str) -> str | None:
        now = datetime.now()
        if re.fullmatch(r"(what('s| is)? )?(the )?(current )?time( is it)?( now)?|what time is it( now)?", low):
            return f"It's {now.strftime('%I:%M %p').lstrip('0')}."
        if re.fullmatch(r"(what('s| is)? )?(the )?(today'?s? )?date( today)?|what day is (it|today)|what is today", low):
            return f"Today is {now.strftime('%A, %d %B %Y')}."
        return None

    def _volume_media(self, low: str, _text: str) -> str | None:
        table = (
            (r"(turn |volume )?(up|increase|raise)( the)?( volume)?|volume up|louder", "media_volume_up", "Volume up."),
            (r"(turn |volume )?(down|decrease|lower|reduce)( the)?( volume)?|volume down|quieter", "media_volume_down", "Volume down."),
            (r"(un)?mute( the)?( sound| volume| audio)?", "media_mute", "Toggled mute."),
            (r"(pause|resume|play|stop)( the)?( music| song| video| media)?|play/pause", "media_play_pause", "Done — play/pause."),
            (r"(next|skip)( the)?( song| track)?|skip", "media_next_track", "Next track."),
            (r"(previous|last|go back)( song| track)?|previous", "media_previous_track", "Previous track."),
        )
        for pattern, tool, reply in table:
            if re.fullmatch(pattern, low):
                result = self._run(tool)
                return reply if "error" not in result else f"I couldn't do that: {result['error']}"
        return None

    def _timer(self, low: str, text: str) -> str | None:
        unit = r"(seconds?|secs?|minutes?|mins?|hours?|hrs?)"
        amount = r"(\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|sixty|half)"
        m = re.fullmatch(rf"(?:set |start )?(?:a |an )?(?:{amount} {unit} )?timer(?: (?:for|of))?(?: {amount} {unit})?", low)
        if m:
            parts = [g for g in m.groups() if g]
            if len(parts) >= 2:
                seconds = _duration_seconds(parts[0], parts[1])
                if seconds:
                    result = self._run("set_timer", seconds=seconds, message="Your timer is done")
                    return f"Timer set for {_nice(seconds)}." if "error" not in result else result["error"]
        m = re.fullmatch(rf"remind me (?:in {amount} {unit}) (?:to |that )?(.+)", low)
        if m:
            seconds = _duration_seconds(m.group(1), m.group(2))
            if seconds:
                message = text[text.lower().rindex(m.group(3).lower()):] if m.group(3).lower() in text.lower() else m.group(3)
                result = self._run("set_timer", seconds=seconds, message=message)
                return f"OK, I'll remind you in {_nice(seconds)}: {message}." if "error" not in result else result["error"]
        return None

    def _todo_note(self, low: str, text: str) -> str | None:
        m = re.fullmatch(r"add (.+?) (?:to|on) (?:my )?(?:to-?do|todo|task|to do)(?: list)?", low) \
            or re.fullmatch(r"(?:add )?(?:to-?do|todo|task)[: ]+(.+)", low)
        if m:
            item = self._original(text, m.group(1))
            result = self._run("add_todo", text=item)
            return f"Added “{item}” to your list." if "error" not in result else result["error"]
        if re.fullmatch(r"(what'?s|what is|show|read)( me)?( on)?( my)? ?(to-?dos?|todo list|to do list|list|tasks)", low) \
                or low in ("what should i do next", "what do i have to do"):
            todos = self._run("list_todos").get("todos", [])
            if not todos:
                return "Your to-do list is empty."
            return "On your list: " + "; ".join(f"{t['id']}. {t['text']}" for t in todos) + "."
        m = re.fullmatch(r"(?:mark |complete |finish )(.+?)(?: as)?(?: done| complete| finished)?", low) \
            if low.startswith(("mark ", "complete ", "finish ")) else None
        if m:
            result = self._run("complete_todo", which=m.group(1).strip())
            return f"Done: {result['text']}." if "error" not in result else result["error"]
        m = re.fullmatch(r"(?:take a note|note|save a note|add a note)[: ]+(?:that )?(.+)", low)
        if m:
            note = self._original(text, m.group(1))
            result = self._run("add_note", text=note)
            return "Noted." if "error" not in result else result["error"]
        if re.fullmatch(r"(show|read|what are)( me)?( my)? notes", low):
            notes = self._run("list_notes").get("notes", [])
            return ("Your notes: " + "; ".join(n["text"] for n in notes) + ".") if notes else "You have no notes."
        return None

    @staticmethod
    def _original(text: str, lowered_part: str) -> str:
        """The user's own capitalisation for a captured piece of text."""
        index = text.lower().find(lowered_part.lower())
        return text[index:index + len(lowered_part)] if index >= 0 else lowered_part

    def _math(self, low: str, _text: str) -> str | None:
        expression = re.sub(r"^(what('s| is)|calculate|compute|how much is|solve)\s+", "", low)
        expression = _spoken_math(expression)
        if not re.search(r"\d", expression) or not re.fullmatch(r"[\d\s+\-*/().%^]+", expression):
            return None
        if not re.search(r"[+\-*/%]", expression):
            return None
        try:
            value = _safe_eval(expression.strip())
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError):
            return None
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        elif isinstance(value, float):
            value = round(value, 6)
        return f"{value}"

    def _open_app(self, low: str, fallback: bool) -> str | None:
        m = re.fullmatch(r"(?:open|launch|start|run)(?: up)?(?: the)?(?: app| application)? (.+)", low)
        if not m:
            return None
        name = m.group(1).strip()
        if len(name.split()) > 3:
            return None
        result = self._run("open_application", app_name=name)
        if "error" in result:
            return f"I couldn't open {name}." if fallback else None
        return f"Opening {name}."
