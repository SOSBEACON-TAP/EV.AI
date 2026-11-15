"""
tools/utilities.py
------------------
Small everyday helpers the AI can call instead of guessing: exact maths, unit conversion, date arithmetic, the time in
another city and dice/coins. Everything here is pure Python, needs no internet and touches nothing on the computer.
"""
from __future__ import annotations

import ast
import datetime as dt
import math
import operator
import random
import re

# --------------------------------------------------------------------------------------------- calculate
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
          "atan": math.atan, "log": math.log, "log10": math.log10, "log2": math.log2, "exp": math.exp, "abs": abs,
          "round": round, "floor": math.floor, "ceil": math.ceil, "factorial": math.factorial,
          "radians": math.radians, "degrees": math.degrees, "min": min, "max": max}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval(node, depth: int = 0):
    if depth > 40:
        raise ValueError("that expression is too deeply nested")
    if isinstance(node, ast.Expression):
        return _eval(node.body, depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_eval(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        a, b = _eval(node.left, depth + 1), _eval(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and (abs(b) > 1000 or (abs(a) > 1e6 and abs(b) > 50)):
            raise ValueError("that power is too large to work out")
        return _BIN[type(node.op)](a, b)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        args = [_eval(a, depth + 1) for a in node.args]
        if node.func.id == "factorial" and (not args or args[0] > 500):
            raise ValueError("that factorial is too large")
        return _FUNCS[node.func.id](*args)
    raise ValueError("only numbers, + - * / // % **, brackets, pi, e and common functions (sqrt, sin, log...) are allowed")


def calculate(expression: str) -> dict:
    """Work out a maths expression exactly, e.g. '(12.5 * 8) / 3 + sqrt(49)'."""
    text = (expression or "").strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", "")
    if not text:
        return {"error": "Give me an expression to work out."}
    if len(text) > 300:
        return {"error": "That expression is too long."}
    try:
        result = _eval(ast.parse(text, mode="eval"))
    except ZeroDivisionError:
        return {"error": "That divides by zero."}
    except (ValueError, SyntaxError, TypeError, OverflowError) as e:
        return {"error": f"I couldn't work that out: {e}"}
    if isinstance(result, float):
        result = round(result, 10)
        if result == int(result) and abs(result) < 1e15:
            result = int(result)
    return {"expression": expression.strip(), "result": result}


# --------------------------------------------------------------------------------------------- units
# every unit -> how many of the base unit of its kind (metre, gram, litre, second, byte, m/s, square metre)
_UNITS = {
    "length": {"m": 1, "meter": 1, "metre": 1, "km": 1000, "kilometer": 1000, "kilometre": 1000, "cm": 0.01, "mm": 0.001,
               "mi": 1609.344, "mile": 1609.344, "yd": 0.9144, "yard": 0.9144, "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
               "in": 0.0254, "inch": 0.0254, "nmi": 1852},
    "mass": {"g": 1, "gram": 1, "kg": 1000, "kilogram": 1000, "mg": 0.001, "t": 1e6, "tonne": 1e6, "lb": 453.59237,
             "pound": 453.59237, "oz": 28.349523125, "ounce": 28.349523125, "stone": 6350.29318},
    "volume": {"l": 1, "liter": 1, "litre": 1, "ml": 0.001, "gal": 3.785411784, "gallon": 3.785411784,
               "qt": 0.946352946, "quart": 0.946352946, "pt": 0.473176473, "pint": 0.473176473, "cup": 0.2365882365,
               "floz": 0.0295735296, "tbsp": 0.0147867648, "tsp": 0.00492892159, "m3": 1000},
    "time": {"s": 1, "sec": 1, "second": 1, "ms": 0.001, "min": 60, "minute": 60, "h": 3600, "hr": 3600, "hour": 3600,
             "day": 86400, "week": 604800, "year": 31557600},
    "speed": {"m/s": 1, "kmh": 1 / 3.6, "km/h": 1 / 3.6, "kph": 1 / 3.6, "mph": 0.44704, "knot": 0.514444, "kn": 0.514444,
              "ft/s": 0.3048},
    "data": {"b": 1, "byte": 1, "kb": 1000, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 1024, "mib": 1024 ** 2,
             "gib": 1024 ** 3, "tib": 1024 ** 4, "bit": 0.125},
    "area": {"m2": 1, "km2": 1e6, "cm2": 1e-4, "ha": 1e4, "hectare": 1e4, "acre": 4046.8564224, "ft2": 0.09290304,
             "sqft": 0.09290304, "mi2": 2589988.110336},
}
_TEMP = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}


def _unit_key(u: str) -> str:
    u = (u or "").strip().lower().replace("°", "").replace(" ", "").replace("square", "")
    for suffix in ("meters", "metres", "kilometers", "kilometres", "miles", "yards", "inches", "pounds", "ounces",
                   "grams", "kilograms", "liters", "litres", "gallons", "seconds", "minutes", "hours", "days", "weeks",
                   "years", "cups", "bytes"):
        if u == suffix:
            return u[:-1] if u not in ("inches",) else "inch"
    return {"celcius": "celsius", "fahrenheit": "f", "celsius": "c", "kelvin": "k", "kmph": "kmh", "metersec": "m/s"}.get(u, u)


def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert between units of length, mass, volume, time, speed, data size, area and temperature."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return {"error": "The value must be a number."}
    a, b = _unit_key(from_unit), _unit_key(to_unit)
    if a in _TEMP and b in _TEMP:
        a, b = a[0], b[0]
        c = value if a == "c" else (value - 32) * 5 / 9 if a == "f" else value - 273.15
        out = c if b == "c" else c * 9 / 5 + 32 if b == "f" else c + 273.15
        return {"value": value, "from": from_unit, "to": to_unit, "result": round(out, 6)}
    for kind, table in _UNITS.items():
        if a in table and b in table:
            return {"value": value, "from": from_unit, "to": to_unit, "kind": kind,
                    "result": round(value * table[a] / table[b], 8)}
    return {"error": f"I can't convert {from_unit!r} to {to_unit!r}. I know length, mass, volume, time, speed, data "
                     "size, area and temperature, and both units must be the same kind."}


# --------------------------------------------------------------------------------------------- dates
def _parse_date(text: str) -> dt.date:
    t = (text or "").strip().lower()
    today = dt.date.today()
    if t in ("today", "now"):
        return today
    if t == "tomorrow":
        return today + dt.timedelta(days=1)
    if t == "yesterday":
        return today - dt.timedelta(days=1)
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", t)           # day first, like 14-11-2026
    if m:
        return dt.date(int(m[3]), int(m[2]), int(m[1]))
    raise ValueError(f"I don't understand the date {text!r}. Use YYYY-MM-DD or DD-MM-YYYY (or today / tomorrow).")


def date_math(operation: str, date: str = "today", other_date: str = "", days: int = 0) -> dict:
    """Date arithmetic. operation: days_until, days_between, add_days or weekday."""
    op = (operation or "").strip().lower()
    try:
        d1 = _parse_date(date)
        if op == "days_until":
            n = (d1 - dt.date.today()).days
            return {"date": d1.isoformat(), "weekday": d1.strftime("%A"), "days_from_today": n,
                    "meaning": f"{abs(n)} day(s) {'from now' if n >= 0 else 'ago'}"}
        if op == "days_between":
            d2 = _parse_date(other_date)
            return {"from": d1.isoformat(), "to": d2.isoformat(), "days": (d2 - d1).days, "weeks": round((d2 - d1).days / 7, 2)}
        if op == "add_days":
            r = d1 + dt.timedelta(days=int(days))
            return {"start": d1.isoformat(), "days_added": int(days), "result": r.isoformat(), "weekday": r.strftime("%A")}
        if op == "weekday":
            return {"date": d1.isoformat(), "weekday": d1.strftime("%A")}
    except (ValueError, OverflowError) as e:
        return {"error": str(e)}
    return {"error": "operation must be days_until, days_between, add_days or weekday."}


# --------------------------------------------------------------------------------------------- world time
_ZONES = {"london": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin", "madrid": "Europe/Madrid",
          "rome": "Europe/Rome", "moscow": "Europe/Moscow", "dubai": "Asia/Dubai", "delhi": "Asia/Kolkata",
          "india": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "chennai": "Asia/Kolkata", "kolkata": "Asia/Kolkata",
          "bangalore": "Asia/Kolkata", "karachi": "Asia/Karachi", "dhaka": "Asia/Dhaka", "bangkok": "Asia/Bangkok",
          "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong", "beijing": "Asia/Shanghai",
          "shanghai": "Asia/Shanghai", "tokyo": "Asia/Tokyo", "seoul": "Asia/Seoul", "sydney": "Australia/Sydney",
          "auckland": "Pacific/Auckland", "new york": "America/New_York", "washington": "America/New_York",
          "chicago": "America/Chicago", "denver": "America/Denver", "los angeles": "America/Los_Angeles",
          "san francisco": "America/Los_Angeles", "toronto": "America/Toronto", "vancouver": "America/Vancouver",
          "mexico city": "America/Mexico_City", "sao paulo": "America/Sao_Paulo", "cairo": "Africa/Cairo",
          "lagos": "Africa/Lagos", "nairobi": "Africa/Nairobi", "johannesburg": "Africa/Johannesburg", "utc": "UTC"}
# used only when the computer has no time-zone database: standard time, daylight saving NOT applied
_FIXED = {"Europe/London": 0, "Europe/Paris": 1, "Europe/Berlin": 1, "Europe/Madrid": 1, "Europe/Rome": 1,
          "Europe/Moscow": 3, "Asia/Dubai": 4, "Asia/Kolkata": 5.5, "Asia/Karachi": 5, "Asia/Dhaka": 6, "Asia/Bangkok": 7,
          "Asia/Singapore": 8, "Asia/Hong_Kong": 8, "Asia/Shanghai": 8, "Asia/Tokyo": 9, "Asia/Seoul": 9,
          "Australia/Sydney": 10, "Pacific/Auckland": 12, "America/New_York": -5, "America/Chicago": -6,
          "America/Denver": -7, "America/Los_Angeles": -8, "America/Toronto": -5, "America/Vancouver": -8,
          "America/Mexico_City": -6, "America/Sao_Paulo": -3, "Africa/Cairo": 2, "Africa/Lagos": 1,
          "Africa/Nairobi": 3, "Africa/Johannesburg": 2, "UTC": 0}


def world_time(place: str) -> dict:
    """The current local time in a city or time zone (e.g. 'Tokyo', 'New York', 'Asia/Kolkata')."""
    key = (place or "").strip()
    if not key:
        return {"error": "Which city or time zone?"}
    zone = _ZONES.get(key.lower(), key)
    now_utc = dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        local = now_utc.astimezone(ZoneInfo(zone))
        note = ""
    except Exception:
        if zone not in _FIXED:
            return {"error": f"I don't know the time zone for {place!r}. Try a big city or a name like 'Asia/Tokyo'."}
        local = now_utc.astimezone(dt.timezone(dt.timedelta(hours=_FIXED[zone])))
        note = "approximate: this computer has no time-zone database, so daylight saving is not applied"
    out = {"place": place, "zone": zone, "time": local.strftime("%H:%M"), "date": local.strftime("%A %d %B %Y"),
           "utc_offset": local.strftime("%z")}
    if note:
        out["note"] = note
    return out


# --------------------------------------------------------------------------------------------- dice & coins
def roll_dice(sides: int = 6, count: int = 1, flip_coin: bool = False) -> dict:
    """Roll one or more dice (any number of sides) or flip a coin."""
    if flip_coin:
        return {"coin": random.choice(["heads", "tails"])}
    try:
        sides, count = int(sides), int(count)
    except (TypeError, ValueError):
        return {"error": "sides and count must be whole numbers."}
    if not 2 <= sides <= 1000 or not 1 <= count <= 50:
        return {"error": "Use 2 to 1000 sides and 1 to 50 dice."}
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {"sides": sides, "rolls": rolls, "total": sum(rolls)}


def pick_random(options: list) -> dict:
    """Pick one option at random from a list (settle 'which one?' decisions)."""
    items = [str(o).strip() for o in (options or []) if str(o).strip()]
    if len(items) < 2:
        return {"error": "Give me at least two options to pick from."}
    return {"options": items[:50], "picked": random.choice(items[:50])}


def text_stats(text: str) -> dict:
    """Counts for a piece of text: words, characters, sentences, lines and reading time."""
    t = text or ""
    if not t.strip():
        return {"error": "There's no text to count."}
    words = len(re.findall(r"\S+", t))
    sentences = max(1, len(re.findall(r"[.!?]+(?:\s|$)", t)))
    return {"words": words, "characters": len(t), "characters_no_spaces": len(re.sub(r"\s", "", t)),
            "sentences": sentences, "lines": len(t.splitlines()) or 1,
            "reading_time_minutes": round(words / 230, 1), "speaking_time_minutes": round(words / 150, 1)}
