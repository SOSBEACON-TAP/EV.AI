EV AI 1.0.11

NEW
- Long-term memory: older chat messages are condensed into a short summary saved on your PC (data/convo_summary.json), and your saved facts are included with each request, so EV AI remembers earlier conversations even after a restart without sending the whole history. Passwords and keys are never stored. Saying "clear memory" wipes it. Turn it off with the long_term_memory setting.
- Sci-fi status text under the loading bar on the startup screen and the update screen (BOOTING CORE SYSTEMS, INITIALIZING NEURAL LINK, LOADING AI MODULES ...), changing as the bar fills.

---

EV AI 1.0.10

FIXES
- Fixed the update getting stuck after you press Restart: EV AI now closes completely, the update helper no longer shows a console window, and it ends a stuck EV AI after a few seconds so the new version is installed and started.
- The update helper writes data/update_log.txt so a failed update can be diagnosed.

NOTE
- If you are on 1.0.9 or older, install this version by hand once: unzip EV_AI-Windows.zip and copy the EV_AI folder's contents over your EV AI folder, choosing Replace. Updates from inside the app work from this version on.

---

EV AI 1.0.9

NEW
- New loading screen: the rotating EV logo above a segmented loading bar, with the loading text under the bar (gold when Jarvis was on). The startup transition animation is gone.
- New update screen: while an update downloads, a full black screen with turning gears and a progress bar shows the real percentage.
- EV AI now adds itself to the Start menu with its logo, so you can find it like any app and pin it to the taskbar (right-click, Pin to taskbar).

IMPROVEMENTS
- The face scan at startup no longer shows text under the camera preview.
- Settings is simpler: Maintenance (Python cache options), Update log and Start at Windows login were removed. Save conversation and Open data folder are kept under Data.

FIXES
- Fixed "The update doesn't contain EV_AI.exe. Not installing." when updating the standalone app.

---

EV AI 1.0.8

FIXES
- Error Doctor no longer reports bundled packages (PySide6, OpenCV, numpy, pyautogui, mediapipe and others) as missing in the standalone app, and no longer suggests venv commands there.

---

EV AI 1.0.7

NEW
- Standalone Windows app: download the zip, unzip, double-click EV_AI.exe. No Python or other install needed. SmartScreen may warn the first time (choose More info, then Run anyway).
- Automatic updates for the standalone app: Settings, Check for updates downloads the new version and restarts into it. Your keys, settings, memory and database are kept.
- Face recognition setup: Settings, Startup face check, Face recognition setup. It captures your face from the webcam inside the app and can turn the startup check on or off (button next to it).
- New look for EV: violet aurora style with rounded panels and gradient buttons. Jarvis keeps its own gold square console look, so the two modes look clearly different.
- Android app: landscape dashboard like the PC, a Portrait option (Settings, Screen layout) that fits the whole screen, Jarvis keeps the status panel, personality moved to Settings.

IMPROVEMENTS
- The left panel is more compact so every button is visible without scrolling.
- Mode buttons no longer shrink so small that their names disappear.
- The standalone download is smaller (unused Qt parts, jax, scipy and offline speech models removed).

FIXES
- Update helper no longer skips program files inside folders named data.

---

# EV AI 1.0.6

NEW
- Quick Actions: a window (Settings → Quick Actions) to create, edit, run and delete your own one-word commands such as "study mode" that open several apps and sites at once. Say "run study mode" or press Run.
- Focus Mode (replaces Study mode): a 🎯 FOCUS button that turns on the quiet corner mode, runs your Quick Action, and closes (or warns about) the sites and apps you block, such as YouTube, Scratch and Discord. Settings → Focus Mode.
- Personality: choose Professional, Friendly or Humorous replies, each with its own voice, speed and pitch (pick the voices in Settings → Personality, with a preview button).
- Personalization: text size, window opacity, a custom theme with your own colours, and saved looks (presets).
- App Usage Insights: see how long you spend in each app, top apps, categories (Coding, Study, Browsing, Entertainment) and a 7-day trend. Stored only on your computer; pause, exclude apps or clear history any time. Ask EV: "how much time did I spend coding today?"
- AI File Finder: find files by describing them ("my EV AI python file", "images in Downloads", "my Arduino projects"), then open the file or its folder. Searches file names only. Ask EV: "open the second result".
- Clipboard assistant: "summarize my clipboard" or "rewrite what I copied", plus buttons in Settings.
- Error Doctor: Settings → Error Doctor checks packages, AI key, internet, webcam and the log, and shows how to fix each problem.

- Jarvis: a SWITCH TO JARVIS button above the core turns the whole core gold and swaps in a system-monitoring-only view: live CPU, memory, disk and battery bars, network and uptime, plus Full Status Report, Top Processes, Disk Space, Battery, Network and Health Check buttons. Jarvis speaks a warning if CPU, memory or disk stay high or the battery runs low. Jarvis only answers computer questions; switch back to EV for everything else.

- Connected device: Settings → Connected device. Enter your phone's device code and EV connects to it. If you give EV a task and the computer is switched off before it finishes, EV rings your phone in the app over the internet, like a WhatsApp call, so no SIM balance is needed.

---

# EV AI 1.0.4

(Gesture control update. 1.0.3 changes are listed below.)

## New
- **New logo** — the red/blue web-atom is now the app and taskbar icon.
- **Startup animation, inside the app** — the logo fills the window, then slowly shrinks and morphs into the glowing core in the middle.
- **Video mode** — opens a small camera window with a reticle that locks onto your eye and follows you. Shrink it to a badge with —, resize by dragging the corner.
- **Compact HUD** — the HUD for the other modes is now a small corner window (no full-screen dimming) with a shrink button and a 🎥 Video button. Song mode can shrink too.
- **8 new themes** — Crimson, Emerald, Violet neon, Ocean, Gold, Sunset, Midnight indigo, Mono. Settings → Appearance, with live preview.
- **New gesture control** (Video mode) — two hands together/apart = zoom; one-hand swipe = next/previous Chrome tab; both hands swipe = switch virtual desktop; hand up/down = volume; hold 1/2/3 fingers = Win+1/2/3; hold an open palm = pause, hold a fist = resume. Settings → Gesture control explains every gesture and lets you tune thresholds and cooldowns. The old gesture set was replaced. The camera also runs faster.

## Fixes
- Closing EV AI to the tray no longer keeps the webcam locked (the Windows Camera app works again). New tray item: **Release camera**.
- WhatsApp sending is more reliable: finds chats by partial / any-case name, copes with WhatsApp Web layout changes, checks the message was sent, and saves a screenshot if something fails.
- Startup animation errors are logged to data/animation_error.log (scripts/test_animation.py plays it on its own).

---
# EV AI 1.0.1

## New
- **Startup animation** — when loading finishes, the centre geometry expands across the screen, then shrinks into the app.
- **Self-update** — Settings → System & About → Check for updates downloads, verifies and installs new versions (your `.env`, data and keys are never touched).
- **Profiles** — Study / Gaming / Work modes.
- **Privacy center**, **offline mode**, **image help** (attach or drag a picture and ask about it).
- **Reminders, to-dos and notes** that survive restarts.
- **Email** — send, read inbox, summarize, contacts; **morning briefing**; **global hotkey**; **start hidden in tray**.
- **Video mode, Song mode**, more hand gestures.
- Settings: search box, live theme/voice preview, hover-sound switch, export/import/reset settings, diagnostics.

## Fixes
- Taskbar now shows the EV atom icon and the app can be pinned.
