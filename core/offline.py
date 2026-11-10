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

        for step in (self._creator, self._find_phone, self._chrome, self._shorts, self._time, self._volume_media, self._timer, self._clock_reminder,
                     self._todo_note, self._math, self._fun_tools):
            reply = step(low, text)
            if reply:
                return reply
        return self._open_app(low, fallback)

    # -- handlers -------------------------------------------------------------
    def _creator(self, low: str, _text: str) -> str | None:
        if re.search(r"\bwho (invented|created|made|built|developed|designed|programmed|owns|is the (creator|inventor|developer|father))\b.*\b(you|ev|ev ai|ev\.ai)\b"
                     r"|\bwho('s| is) (your|the) (creator|inventor|developer|maker|owner)\b"
                     r"|\bwho (are your|is your) (creator|inventor|developer|maker)s?\b"
                     r"|\b(your|ev'?s?) (creator|inventor|developer)\b.*\bwho\b", low):
            return "I was invented by Shri Nikil Prakash."
        return None

    def _shorts(self, low: str, _text: str) -> str | None:
        if re.search(r"how many (shorts|reels)|(shorts|reels) (count|today)|count (of )?(my )?(shorts|reels)", low):
            from core import shorts
            return shorts.summary()
        return None

    def _chrome(self, low: str, text: str) -> str | None:
        """Voice control of Chrome through the EV AI extension (only when the extension is connected)."""
        from core import browser_bridge
        b = browser_bridge.get()
        if b is None or not b.connected:
            return None
        low = re.sub(r"^(please |hey ev |ev )", "", low).strip(" .!")
        sends = (
            (r"scroll down|page down", {"action": "scroll", "dir": "down"}, "Scrolling down."),
            (r"scroll up|page up", {"action": "scroll", "dir": "up"}, "Scrolling up."),
            (r"(scroll|go) to (the )?top( of (the )?page)?", {"action": "scroll", "dir": "top"}, "Back to the top."),
            (r"(scroll|go) to (the )?(bottom|end)( of (the )?page)?", {"action": "scroll", "dir": "bottom"}, "Down to the bottom."),
            (r"next tab|switch to (the )?next tab", {"action": "next_tab"}, "Next tab."),
            (r"(previous|last|prev) tab", {"action": "prev_tab"}, "Previous tab."),
            (r"close (this |the |current )?tab", {"action": "close_tab"}, "Tab closed."),
            (r"(open )?(a )?new tab", {"action": "new_tab"}, "New tab."),
            (r"go back|back a page|previous page", {"action": "back"}, "Going back."),
            (r"go forward|forward a page|next page", {"action": "forward"}, "Going forward."),
            (r"unmute (all )?(the )?tabs?", {"action": "unmute_tabs"}, "Tabs unmuted."),
            (r"mute (all )?(the )?(tabs?|browser)", {"action": "mute_tabs"}, "Tabs muted."),
            (r"close (all )?(the )?duplicate tabs?", {"action": "close_duplicates"}, "Closing duplicate tabs."),
            (r"(reload|refresh)( this| the)?( page)?", {"action": "reload"}, "Reloading."),
        )
        for pattern, cmd, reply in sends:
            if re.fullmatch(pattern, low):
                b.send(cmd)
                return reply
        if re.fullmatch(r"(summari[sz]e|explain|read|describe)( this| the)?( web)? ?page( to me)?|what('s| is) (this|on this) page( about)?\??|what is this site about\??", low):
            b.ask_about_page("Summarise this page briefly." if re.match(r"summari|read", low) else "What is this page about?")
            return "Reading the page in Chrome..."
        m = re.fullmatch(r"(?:click|press|tap)( on)? (.+)", low)
        if m:
            b.send({"action": "click", "text": m.group(2)})
            return f"Clicking {m.group(2)}."
        m = re.fullmatch(r"(?:google|search google for|search chrome for) (.+)|search (?:for )?(.+) (?:in|on) chrome", low)
        if m:
            q = next(g for g in m.groups() if g)
            b.send({"action": "search", "query": q})
            return f"Searching for {q}."
        m = re.fullmatch(r"open (.+) in chrome", low)
        if m:
            b.send({"action": "open_url", "url": m.group(1).replace(" dot ", ".").replace(" ", "")})
            return f"Opening {m.group(1)}."
        m = re.fullmatch(r"switch to (.+?)( tab)?", low)
        if m and m.group(2):
            b.send({"action": "switch_tab", "text": m.group(1)})
            return f"Switching to {m.group(1)}."
        return None

    def _find_phone(self, low: str, _text: str) -> str | None:
        if re.fullmatch(r"(find|ring|locate|call) (my |the )?(phone|mobile)|where('s| is) my (phone|mobile)|i lost my (phone|mobile)", low):
            from core import devices
            ok, msg = devices.find_phone()
            return msg
        return None

    def _clock_reminder(self, low: str, text: str) -> str | None:
        """'remind me at 5:30 pm to call mom' / 'remind me tomorrow at 9 to ...' (no AI needed)."""
        m = re.fullmatch(r"remind me (tomorrow )?(?:at )(\d{1,2})(?::(\d{2}))? ?(am|pm|a\.m\.|p\.m\.)? (?:to |that |about )?(.+)", low)
        if not m:
            return None
        tomorrow, hh, mm, ap, msg = m.groups()
        hour, minute = int(hh), int(mm or 0)
        if ap:
            pm = ap.startswith("p")
            if hour == 12:
                hour = 12 if pm else 0
            elif pm:
                hour += 12
        if hour > 23 or minute > 59:
            return None
        from datetime import datetime, timedelta
        now = datetime.now()
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if tomorrow or due <= now:
            due += timedelta(days=1)
        message = text[text.lower().rindex(msg.lower()):] if msg.lower() in text.lower() else msg
        result = self._run("set_reminder_at", at=due.strftime("%Y-%m-%d %H:%M"), message=message)
        if "error" in result:
            return result["error"]
        return f"Done, I'll remind you {'tomorrow' if due.date() > now.date() else 'today'} at {due.strftime('%I:%M %p').lstrip('0')}: {message}."

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

    # -- small everyday helpers: dice, coin, converter, stopwatch, countdown to a date, jokes --------------
    _JOKES = (
        "Why do programmers prefer dark mode? Because light attracts bugs.",
        "I would tell you a UDP joke, but you might not get it.",
        "Why was the computer cold? It left its Windows open.",
        "There are 10 kinds of people: those who understand binary and those who don't.",
        "A SQL query walks into a bar, walks up to two tables and asks: can I join you?",
        "Why did the developer go broke? Because he used up all his cache.",
        "My password is the last 8 digits of pi. Good luck with that.",
        "Why do Java developers wear glasses? Because they don't C sharp.",
    )
    _UNITS = {  # name -> (group, size in the group's base unit)
        "km": ("len", 1000), "kilometer": ("len", 1000), "kilometers": ("len", 1000), "kilometre": ("len", 1000), "kilometres": ("len", 1000),
        "m": ("len", 1), "meter": ("len", 1), "meters": ("len", 1), "metre": ("len", 1), "metres": ("len", 1),
        "cm": ("len", 0.01), "centimeter": ("len", 0.01), "centimeters": ("len", 0.01),
        "mile": ("len", 1609.344), "miles": ("len", 1609.344), "ft": ("len", 0.3048), "foot": ("len", 0.3048), "feet": ("len", 0.3048),
        "inch": ("len", 0.0254), "inches": ("len", 0.0254),
        "kg": ("mass", 1000), "kilogram": ("mass", 1000), "kilograms": ("mass", 1000), "g": ("mass", 1), "gram": ("mass", 1), "grams": ("mass", 1),
        "lb": ("mass", 453.592), "lbs": ("mass", 453.592), "pound": ("mass", 453.592), "pounds": ("mass", 453.592),
        "liter": ("vol", 1), "liters": ("vol", 1), "litre": ("vol", 1), "litres": ("vol", 1), "l": ("vol", 1),
        "gallon": ("vol", 3.78541), "gallons": ("vol", 3.78541), "ml": ("vol", 0.001),
    }
    _MONTHS = {m: i + 1 for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july",
                                                  "august", "september", "october", "november", "december"))}
    _stopwatch_start = None

    def _fun_tools(self, low: str, _text: str) -> str | None:
        import random
        import time
        if re.fullmatch(r"(flip|toss) (a |the )?coin|heads or tails", low):
            return random.choice(("Heads.", "Tails."))
        m = re.fullmatch(r"roll (a |an |one |(\d+) )?(dice|die)( twice)?", low)
        if m:
            n = int(m.group(2)) if m.group(2) else (2 if m.group(4) else 1)
            n = max(1, min(n, 10))
            rolls = [random.randint(1, 6) for _ in range(n)]
            return f"{rolls[0]}." if n == 1 else f"{', '.join(map(str, rolls))}. Total {sum(rolls)}."
        m = re.fullmatch(r"(pick|give me|choose)( a)? (random )?number (between|from) (-?\d+) (and|to) (-?\d+)", low)
        if m:
            a, b = sorted((int(m.group(5)), int(m.group(7))))
            return str(random.randint(a, b))
        m = re.fullmatch(r"(choose|pick|decide) (between )?(.+?) or (.+)", low)
        if m and "tab" not in low:
            return f"I pick {random.choice((m.group(3), m.group(4)))}."
        if re.fullmatch(r"(tell me )?(a )?joke|make me laugh|tell me something funny", low):
            return random.choice(self._JOKES)
        if re.fullmatch(r"(start|begin) (the |a )?stopwatch", low):
            self._stopwatch_start = time.monotonic()
            return "Stopwatch started."
        if re.fullmatch(r"(stop|end|check|lap)( the)? stopwatch", low):
            if self._stopwatch_start is None:
                return "The stopwatch isn't running. Say start stopwatch first."
            secs = int(time.monotonic() - self._stopwatch_start)
            if low.startswith("stop") or low.startswith("end"):
                self._stopwatch_start = None
            return f"Stopwatch: {_nice(secs) if secs >= 60 else str(secs) + ' second' + ('' if secs == 1 else 's')}."
        m = re.fullmatch(r"(?:convert )?(-?\d+(?:\.\d+)?) ?(?:degrees? )?(c|celsius|f|fahrenheit) (?:to|in|into) (?:degrees? )?(c|celsius|f|fahrenheit)", low)
        if m:
            v, a, b = float(m.group(1)), m.group(2)[0], m.group(3)[0]
            if a == b:
                out = v
            elif a == "c":
                out = v * 9 / 5 + 32
            else:
                out = (v - 32) * 5 / 9
            return f"{v:g} degrees {'Celsius' if a == 'c' else 'Fahrenheit'} is {out:.1f} degrees {'Celsius' if b == 'c' else 'Fahrenheit'}."
        m = re.fullmatch(r"(?:convert )?(-?\d+(?:\.\d+)?) ?([a-z]+) (?:to|in|into) ([a-z]+)", low)
        if m and m.group(2) in self._UNITS and m.group(3) in self._UNITS:
            (ga, sa), (gb, sb) = self._UNITS[m.group(2)], self._UNITS[m.group(3)]
            if ga == gb:
                out = float(m.group(1)) * sa / sb
                return f"{float(m.group(1)):g} {m.group(2)} is {out:,.4g} {m.group(3)}."
            return "Those two units can't be converted into each other."
        m = re.fullmatch(r"(?:how many days|days) (?:until|till|to|left (?:for|until|till)) (\d{1,2})(?:st|nd|rd|th)? (?:of )?([a-z]+)", low)
        if m and m.group(2) in self._MONTHS:
            from datetime import date
            today = date.today()
            try:
                target = date(today.year, self._MONTHS[m.group(2)], int(m.group(1)))
                if target < today:
                    target = date(today.year + 1, target.month, target.day)
            except ValueError:
                return None
            days = (target - today).days
            return "That's today." if days == 0 else f"{days} day{'s' if days != 1 else ''} to go."
        return None

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
