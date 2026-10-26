"""
core/gesture_engine.py
------------------------
The brain of Video-mode gesture control. Pure Python — no camera, no Qt, no
mediapipe — so the rules can be unit-tested with fake hand positions
(scripts/test_gestures.py) and the worker thread stays thin.

Feed it one reading per camera frame: a list of hands, each hand being 21
(x, y) points in 0..1 coordinates of the MIRRORED picture (x grows to your
right, y grows downward). It returns a list of events such as
{"action": "tab_next", "label": "Next tab (Ctrl+Tab)"} that the worker turns
into key presses.

The ten gestures
  1  two hands move toward each other ........ zoom in
  2  two hands move apart .................... zoom out
  3  one hand swipes left .................... next browser tab (Ctrl+Tab)
  4  one hand swipes right ................... previous tab (Ctrl+Shift+Tab)
  5  both hands swipe left together .......... next virtual desktop (Win+Ctrl+Right)
  6  both hands swipe right together ......... previous desktop (Win+Ctrl+Left)
  7  open palm held still .................... pause (fist or palm held = resume)
  8  hand moves down ......................... volume down
  9  hand moves up ........................... volume up
  10 1 / 2 / 3 fingers held ................. Win+1 / Win+2 / Win+3

Everything tunable lives in `cfg` (the gesture_* keys of core/user_prefs.py).
"""

from __future__ import annotations

import math
from collections import deque

WRIST, THUMB_TIP, THUMB_IP = 0, 4, 3
MIDDLE_MCP, PINKY_MCP = 9, 17
_FINGERS = ((8, 6), (12, 10), (16, 14), (20, 18))   # (tip, pip) for index..pinky

# How long, in seconds, of motion is looked at when judging a swipe.
SWIPE_WINDOW = 0.45
# A hand that moved more than this (fraction of the picture) inside the
# window counts as "moving", so a held pose is never confused with a swipe.
STILL_LIMIT = 0.07

# Smoothing: 0 = frozen, 1 = raw. Lower = steadier but laggier.
SMOOTHING = 0.55


def _d(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def finger_states(pts) -> list[bool]:
    """Index, middle, ring, pinky: True when the finger is stretched out.
    Compares tip and middle-joint distance from the wrist, so it still
    works when the hand is tilted or turned."""
    wrist = pts[WRIST]
    return [_d(pts[t], wrist) > _d(pts[p], wrist) * 1.12 for t, p in _FINGERS]


def classify(pts) -> str:
    """'palm', 'fist', 'one', 'two', 'three' or 'other'."""
    ext = finger_states(pts)
    n = sum(ext)
    if n == 4:
        return "palm"
    if n == 0:
        return "fist"
    if ext == [True, False, False, False]:
        return "one"
    if ext == [True, True, False, False]:
        return "two"
    if ext == [True, True, True, False]:
        return "three"
    return "other"


def center(pts) -> tuple[float, float]:
    """Palm centre — steadier than the fingertips."""
    a, b = pts[WRIST], pts[MIDDLE_MCP]
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


DEFAULT_CFG = {
    "gestures_enabled": True,
    "gesture_swipe_distance": 0.25,
    "gesture_swipe_cooldown": 0.6,
    "gesture_zoom_step": 0.06,
    "gesture_zoom_cooldown": 0.12,
    "gesture_volume_distance": 0.14,
    "gesture_volume_cooldown": 0.3,
    "gesture_volume_step": 5,
    "gesture_hold_time": 0.7,
    "gesture_finger_cooldown": 0.8,
    "gesture_pause_hold": 1.0,
    "gesture_resume_mode": "fist",
    "gesture_resume_hold": 1.5,
}

LABELS = {
    "zoom_in": "Zoom in",
    "zoom_out": "Zoom out",
    "tab_next": "Next tab (Ctrl+Tab)",
    "tab_prev": "Previous tab (Ctrl+Shift+Tab)",
    "desktop_next": "Next desktop (Win+Ctrl+Right)",
    "desktop_prev": "Previous desktop (Win+Ctrl+Left)",
    "pause": "Paused",
    "resume": "Resumed",
    "volume_up": "Volume up",
    "volume_down": "Volume down",
    "app_1": "Win+1",
    "app_2": "Win+2",
    "app_3": "Win+3",
}


class GestureEngine:
    def __init__(self, cfg: dict | None = None):
        self.cfg = dict(DEFAULT_CFG)
        if cfg:
            self.cfg.update(cfg)
        self.paused = False
        self.gesture = ""            # what is being seen right now (for the UI)
        self.last_event = ""         # last action label (for the UI)
        self._reset_tracking()
        self._cool: dict[str, float] = {}
        self._single_ok_at = 0.0
        self._smooth: list | None = None

    # -- configuration ----------------------------------------------------
    def set_cfg(self, cfg: dict) -> None:
        self.cfg.update({k: v for k, v in cfg.items() if k in DEFAULT_CFG})

    def set_paused(self, paused: bool) -> None:
        self.paused = bool(paused)
        self._need_release = self.paused
        self._hold_kind, self._hold_start = None, 0.0

    def _reset_tracking(self) -> None:
        self._trail = deque()        # (t, cx, cy) of the single hand
        self._pair = deque()         # (t, mid_x, gap) of the two hands
        self._zoom_ref = None
        self._hold_kind = None
        self._hold_start = 0.0
        self._hold_fired = False
        self._need_release = False
        self._last_vertical = (0.0, 0)   # (time, direction)
        self._last_swipe = (0.0, 0)

    # -- helpers ----------------------------------------------------------
    def _ready(self, name: str, now: float, wait: float) -> bool:
        return now - self._cool.get(name, -1e9) >= wait

    def _fire(self, events: list, action: str, now: float, cool_name: str | None = None) -> None:
        self._cool[cool_name or action] = now
        self.last_event = LABELS.get(action, action)
        events.append({"action": action, "label": self.last_event})

    def _smoothed(self, hands):
        """Exponential smoothing per hand slot (hands sorted left→right so a
        slot keeps following the same hand)."""
        hands = sorted(hands, key=lambda h: h[WRIST][0])
        prev = self._smooth
        if prev is None or len(prev) != len(hands):
            self._smooth = [list(map(tuple, h)) for h in hands]
            return self._smooth
        out = []
        for old, new in zip(prev, hands):
            out.append([(o[0] + (n[0] - o[0]) * SMOOTHING, o[1] + (n[1] - o[1]) * SMOOTHING)
                        for o, n in zip(old, new)])
        self._smooth = out
        return out

    # -- main entry -------------------------------------------------------
    def update(self, hands: list, now: float) -> list[dict]:
        """hands: list of 21-point lists. Returns events fired this frame."""
        events: list[dict] = []
        if not hands:
            self._smooth = None
            self._trail.clear()
            self._pair.clear()
            self._zoom_ref = None
            self._hold_kind = None
            self._need_release = False
            self.gesture = ""
            return events

        hands = self._smoothed(hands[:2])
        cfg = self.cfg

        # ----- paused: only the resume gesture is listened for -----------
        if self.paused:
            self.gesture = "Paused"
            if len(hands) == 1:
                self._handle_resume(classify(hands[0]), center(hands[0]), now, events)
            return events

        if not cfg["gestures_enabled"]:
            self.gesture = "Gestures off"
            return events

        if len(hands) == 2:
            self._trail.clear()
            self._hold_kind = None
            self._single_ok_at = now + 0.5      # let both hands leave before one-hand gestures
            self._two_hands(hands, now, events)
        else:
            self._pair.clear()
            self._zoom_ref = None
            self._one_hand(hands[0], now, events)
        return events

    # -- pause / resume ---------------------------------------------------
    def _handle_resume(self, kind, c, now, events) -> None:
        mode = self.cfg["gesture_resume_mode"]
        want = "palm" if mode == "palm" else "fist"
        if self._need_release:                  # the palm that paused us must go away first
            if kind != "palm":
                self._need_release = False
            return
        if kind == want:
            if self._hold_kind != want:
                self._hold_kind, self._hold_start = want, now
            elif now - self._hold_start >= self.cfg["gesture_resume_hold"]:
                self.paused = False
                self._hold_kind = None
                self._single_ok_at = now + 1.0
                self._trail.clear()
                self._fire(events, "resume", now)
        else:
            self._hold_kind = None

    # -- two hands --------------------------------------------------------
    def _two_hands(self, hands, now, events) -> None:
        a, b = center(hands[0]), center(hands[1])
        gap = _d(a, b)
        mid_x = (a[0] + b[0]) / 2
        self._pair.append((now, mid_x, gap))
        while self._pair and now - self._pair[0][0] > SWIPE_WINDOW:
            self._pair.popleft()
        self.gesture = "Two hands"

        # joint sideways swipe -> virtual desktops
        t0, x0, g0 = self._pair[0]
        dx, dgap = mid_x - x0, gap - g0
        dist = self.cfg["gesture_swipe_distance"]
        if (len(self._pair) >= 3 and abs(dx) >= dist and abs(dgap) < abs(dx) * 0.5
                and self._ready("desktop", now, self.cfg["gesture_swipe_cooldown"])):
            self._fire(events, "desktop_next" if dx < 0 else "desktop_prev", now, "desktop")
            self._pair.clear()
            self._zoom_ref = None
            self.gesture = "Both hands swipe " + ("left" if dx < 0 else "right")
            return

        # moving together / apart -> zoom
        if self._zoom_ref is None:
            self._zoom_ref = gap
            return
        change = gap - self._zoom_ref
        step = self.cfg["gesture_zoom_step"]
        if abs(change) >= step and self._ready("zoom", now, self.cfg["gesture_zoom_cooldown"]):
            self._fire(events, "zoom_in" if change < 0 else "zoom_out", now, "zoom")
            self._zoom_ref = gap
            self.gesture = "Hands together" if change < 0 else "Hands apart"

    # -- one hand ---------------------------------------------------------
    def _one_hand(self, pts, now, events) -> None:
        kind = classify(pts)
        cx, cy = center(pts)
        self._trail.append((now, cx, cy))
        while self._trail and now - self._trail[0][0] > SWIPE_WINDOW:
            self._trail.popleft()
        t0, x0, y0 = self._trail[0]
        dx, dy = cx - x0, cy - y0
        moving = math.hypot(dx, dy) > STILL_LIMIT
        names = {"palm": "Open palm", "fist": "Fist", "one": "1 finger", "two": "2 fingers",
                 "three": "3 fingers"}
        self.gesture = names.get(kind, "Hand")

        if now < self._single_ok_at or len(self._trail) < 3:
            return
        cfg = self.cfg

        # swipe left / right -> tabs
        if (abs(dx) >= cfg["gesture_swipe_distance"] and abs(dy) < abs(dx) * 0.6
                and self._ready("swipe", now, cfg["gesture_swipe_cooldown"])):
            direction = -1 if dx < 0 else 1
            last_t, last_dir = self._last_swipe
            # the hand coming back after a swipe must not fire the opposite one
            if last_dir == -direction and now - last_t < 0.7:
                self._trail.clear()
                return
            self._last_swipe = (now, direction)
            self._fire(events, "tab_next" if dx < 0 else "tab_prev", now, "swipe")
            self._trail.clear()
            self._hold_kind = None
            self.gesture = "Swipe " + ("left" if dx < 0 else "right")
            return

        # up / down -> volume (steps repeat while the movement continues)
        vd = cfg["gesture_volume_distance"]
        if abs(dy) >= vd and abs(dx) < abs(dy) * 0.6 and self._ready("volume", now, cfg["gesture_volume_cooldown"]):
            direction = -1 if dy < 0 else 1            # y shrinks going up
            last_t, last_dir = self._last_vertical
            # the hand coming back after a stroke must not undo it
            if not (last_dir == -direction and now - last_t < 0.7):
                self._fire(events, "volume_up" if direction < 0 else "volume_down", now, "volume")
                self._last_vertical = (now, direction)
                self._trail.clear()
                self.gesture = "Hand " + ("up" if direction < 0 else "down")
                return
            self._trail.clear()          # return stroke: forget it
            return

        # held poses (hand must be still)
        if moving:
            self._hold_kind = None
            return
        if kind == "palm":
            self._hold_pose("palm", now, cfg["gesture_pause_hold"], events, self._do_pause)
        elif kind in ("one", "two", "three"):
            self._hold_pose(kind, now, cfg["gesture_hold_time"], events, self._do_fingers)
        else:
            self._hold_kind = None

    def _hold_pose(self, kind, now, needed, events, action) -> None:
        if self._hold_kind != kind:
            self._hold_kind, self._hold_start, self._hold_fired = kind, now, False
            return
        if not self._hold_fired and now - self._hold_start >= needed:
            self._hold_fired = True
            action(kind, now, events)

    def _do_pause(self, kind, now, events) -> None:
        self.paused = True
        self._need_release = True
        self._hold_kind = None
        self._fire(events, "pause", now)

    def _do_fingers(self, kind, now, events) -> None:
        if self._ready("fingers", now, self.cfg["gesture_finger_cooldown"]):
            self._fire(events, {"one": "app_1", "two": "app_2", "three": "app_3"}[kind], now, "fingers")
