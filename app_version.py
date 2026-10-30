"""Version number and release notes — the ONLY file that changes per release.

Bump VERSION and edit RELEASE_NOTES before running scripts/make_release.py.
(Kept apart from config.py so updates never overwrite your update-check address.)
"""
VERSION = "1.0.8"
BUILD = 37   # goes up with every zip I send you, so you can tell which files are installed
RELEASE_NOTES = (
    "Error Doctor fixed for the standalone app. Standalone Windows app (no Python needed) with automatic updates, Face recognition setup in Settings, a more compact left panel with no scrolling, new violet EV look and a gold-console Jarvis look, Android app with landscape and portrait layouts. Camera fix, new logo, intro animation inside the app, Video mode with eye-tracking HUD, compact HUD, 8 new themes, more reliable WhatsApp, new two-hand gesture control, Quick Actions, Focus Mode, App Usage Insights, AI File Finder, personalities with their own voices, personalization, clipboard assistant, Error Doctor, Jarvis switch (gold look, live system monitor), system status, read screen, custom macros, connected phone that rings in-app if the PC shuts down mid-task."
)
