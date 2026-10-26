"""
core/profiles.py
------------------
One-click bundles of settings: Focus, Gaming, Work (and Default).
Applying a profile sets the listed preferences and switches EV's mode;
it never touches API keys, email or other accounts. Each profile can
also say whether Observe / Video mode should be switched off.
"""

PROFILES = {
    "Default": {
        "mode": "normal",
        "prefs": {"speak_replies": True, "always_on_top": False, "hover_sound": True,
                  "offline_first": False, "global_hotkey": True, "minimize_to_tray": False,
                  "observe_interval_s": 20},
        "stop_observe": False, "stop_video": False,
        "about": "Everyday defaults.",
    },
    "Focus": {
        "mode": "study",
        "prefs": {"speak_replies": False, "always_on_top": False, "hover_sound": False,
                  "offline_first": True, "observe_interval_s": 60},
        "stop_observe": True, "stop_video": True,
        "about": "Focus mode, quiet (no spoken replies or sounds), simple commands answered instantly.",
    },
    "Gaming": {
        "mode": "normal",
        "prefs": {"speak_replies": False, "always_on_top": False, "hover_sound": False,
                  "offline_first": True, "global_hotkey": True, "minimize_to_tray": True},
        "stop_observe": True, "stop_video": True,
        "about": "Stays out of the way: tray + Ctrl+Alt+E hotkey, no sounds, no screen watching.",
    },
    "Work": {
        "mode": "serious",
        "prefs": {"speak_replies": False, "always_on_top": True, "hover_sound": False,
                  "offline_first": True, "global_hotkey": True, "observe_interval_s": 60},
        "stop_observe": False, "stop_video": False,
        "about": "Serious mode, dashboard stays on top, quiet, fast local commands.",
    },
}
