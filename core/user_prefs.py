"""
core/user_prefs.py
--------------------
Small persistent store for the toggles in Settings (theme, speak replies,
always-on-top, auto-clearing __pycache__). Saved as data/user_prefs.json
next to the app — separate from .env, which is for secrets/provider
config you edit by hand, not for things a settings dialog flips.

Standard library only, and deliberately no import of config.py: main.py
reads this before anything else is imported (it decides whether Python
is even allowed to write __pycache__ files), so it has to be cheap and
self-contained. Reads never raise — a missing or corrupt file just means
defaults.
"""

import json
import sys
from pathlib import Path

DEFAULTS = {
    "theme": "dark",             # "dark" | "light"
    "speak_replies": True,       # read replies aloud (TTS)
    "always_on_top": False,      # keep the main window above other apps
    "auto_clear_pycache": True,  # no __pycache__ folders left behind
    "minimize_to_tray": False,   # closing the window hides to the system tray
    "global_hotkey": True,       # Ctrl+Alt+E shows/hides EV from anywhere
    "briefing_on_start": False,  # read out a morning briefing when EV opens
    "offline_first": False,      # answer simple commands locally before asking the AI
    "hover_sound": True,         # soft sound when hovering buttons
    "profile": "Default",        # last applied profile name
    "auto_check_updates": True,  # quietly look for a newer version when EV opens
    "start_in_tray": False,      # launch hidden in the tray (needs minimize_to_tray)
    "observe_interval_s": 20,    # how often Observation mode glances at the screen
    # -- hand-gesture control (Video mode); see core/gesture_engine.py -----
    "gestures_enabled": True,          # master switch for gesture ACTIONS (camera/HUD keep running)
    "gesture_swipe_distance": 0.25,    # how far a swipe must travel (fraction of the picture)
    "gesture_swipe_cooldown": 0.6,     # seconds between swipes
    "gesture_zoom_step": 0.06,         # how far the hands must move together/apart per zoom step
    "gesture_zoom_cooldown": 0.12,     # seconds between zoom steps
    "gesture_volume_distance": 0.14,   # how far the hand must move up/down for a volume step
    "gesture_volume_cooldown": 0.3,   # seconds between volume steps
    "gesture_volume_step": 5,          # percent per volume step
    "gesture_hold_time": 0.7,          # seconds to hold 1/2/3 fingers
    "gesture_finger_cooldown": 0.8,    # seconds before 1/2/3 fingers can fire again
    "gesture_pause_hold": 1.0,         # seconds to hold an open palm to pause
    "gesture_resume_mode": "fist",     # "fist" or "palm": what resumes recognition
    "gesture_resume_hold": 1.5,        # seconds to hold that gesture to resume
    "seen_gesture_guide": False,       # the gesture cheat-sheet has been shown once
    # -- personality ---------------------------------------------------------
    "personality": "default",          # "default" | "professional" | "friendly" | "humorous"
    "voice_per_personality": True,     # each personality speaks with its own voice
    "voice_professional": "en-US-GuyNeural",
    "voice_friendly": "en-US-AriaNeural",
    "voice_humorous": "en-US-DavisNeural",
    # -- Focus Mode ----------------------------------------------------------
    "long_term_memory": True,          # keep a condensed summary of older chats on this PC
    "start_menu_target": "",           # where EV_AI.exe was when its Start menu entry was made
    "jarvis_ui": False,                # the yellow Jarvis look + tools is switched on
    "device_id": "",                   # secret id from the connected phone's device code
    "device_server": "",               # alert server (blank = ntfy.sh)
    "call_on_shutdown": True,          # call that phone if the PC shuts down mid-task
    "focus_chain": "focus mode",       # saved Quick Action to run when Focus Mode starts
    "focus_blocked": "youtube, scratch, discord",   # sites / apps to block while focusing
    "focus_action": "close",           # "close" the distraction, or just "warn"
    # -- App Usage Insights ----------------------------------------------------
    "usage_tracking": True,            # record which app is in front (local only)
    "usage_excluded": "",              # programs never recorded, comma separated
    # -- File Finder -------------------------------------------------------------
    "finder_folders": "",              # extra folders to search (semicolon separated)
    # -- sending -------------------------------------------------------------------
    "confirm_before_sending": False,   # ask "are you sure?" before sending email / WhatsApp
    # -- personalization -----------------------------------------------------
    "font_scale": 100,                 # interface text size, percent
    "window_opacity": 100,             # main window opacity, percent (60-100)
    "custom_accent1": "#F0465A",       # custom theme: left/status accent
    "custom_accent2": "#3C8CF0",       # custom theme: right/action accent
    "custom_bg": "#10131E",            # custom theme: background
    "presets_json": "{}",              # saved looks: name -> settings
}

GESTURE_KEYS = tuple(k for k in DEFAULTS if k.startswith("gesture"))


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _path() -> Path:
    return _root() / "data" / "user_prefs.json"


def load() -> dict:
    prefs = dict(DEFAULTS)
    try:
        stored = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            for key in DEFAULTS:
                if key in stored and isinstance(stored[key], type(DEFAULTS[key])):
                    prefs[key] = stored[key]
    except (OSError, ValueError):
        pass
    return prefs


def get(key: str):
    return load()[key]


def set_value(key: str, value) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    prefs = load()
    prefs[key] = value
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[EV AI] Couldn't save preferences: {e}")
