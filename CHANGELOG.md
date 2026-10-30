# EV.AI — Update Log

Everything built, stage by stage, oldest first. Shown in-app via
Settings -> Update Log. New entries get added here (at the bottom) as
changes are made, going forward.

## Stage 1 — UI shell + config
- Dashboard window: status/system/mode panels, AI core animation,
  conversation view, command input.
- State machine (idle/listening/thinking/speaking/error) wired to a stub
  text pipeline, before any real AI was connected.

## Stage 2 — Voice input/output
- Wake word ("Hey EV"), clap-to-activate listening.
- Text-to-speech replies (pyttsx3, later an Edge TTS option).

## Stage 3 — Real AI brain
- Connected to a real AI provider (Anthropic / Gemini / Groq, chosen via
  AI_PROVIDER in .env).

## Stage 4 — Tool calling
- The AI brain can call tools instead of just replying with text.

## Stage 5-6 — Tool registry + confirmation gating
- Many more tools registered through a central router.
- Sensitive tools (anything irreversible/destructive) require explicit
  confirmation before running.

## Stage 7 — Memory
- SQLite-backed memory store for durable facts and reminders EV should
  still know after a restart.

## Stage 8 — Smarter automation
- Recurring scheduled tasks (daily/weekly), persisted and polled in the
  background.

## Stage 9 — Real-world actions
- Real document creation: .docx, .pdf, .xlsx.
- Email via SMTP (send_email).
- WhatsApp Web automation (send_whatsapp_message) via Playwright — fixed
  a bug where the AI picked the wrong tool and opened Edge instead of
  the automated Chromium window; also fixed the QR-scan timeout.
- General browser control (open/search/click, spoken commands).
- Live dictation + keyboard control (type_text, press_key).

## Stage 10 — Startup security, Video mode, polish
- Startup face check: webcam verifies the enrolled owner before the app
  opens, with a live camera preview and a progress bar.
- Windows autostart (runs at login, no console window).
- Password fallback for the face check (Settings -> set/change it) —
  used only if the face scan fails or the camera isn't available.
- Video mode: pinch-to-zoom hand gesture, plus open-palm (play/pause),
  fist (mute), victory sign (next track), and open-palm swipe (switch
  virtual desktop) — all via a background webcam thread (mediapipe),
  pinned to mediapipe==0.10.21 after a newer release removed the API
  this depends on.
- HUD overlay (shown during Automatic/Serious/Study/Observation modes):
  repositioned to the right side of the screen, with a new left-side
  panel showing the video preview and an on/off toggle, usable from
  inside the HUD, not just the main dashboard.
- Settings panel (gear icon, top right) replacing the static
  "SYSTEM ONLINE" label — build/AI-provider info, face-check status,
  password fallback, autostart enable/disable, and this update log.
- In-app Activity Log (Settings -> View log) — a live copy of everything
  EV.AI prints, since the silent/autostart launch path has no console to
  read errors from.
- Removed the dashboard's permanent "BUILD INFO" panel (moved into
  Settings) to make room for Quick Actions.
- Renamed the app from "EV AI" to "EV.AI" throughout the UI.
- Launching now runs silently (pythonw, no console window) by default;
  `boot_debug.bat` still opens a console for troubleshooting.
- Fixed: silent launch (boot.bat / pythonw) left the startup screen stuck
  at 0% — pythonw has no console, so sys.stdout is None and the new log
  capture crashed on the first print. Log capture now tolerates that.
- Startup screen now has a close button (top-right) and Esc to quit, so a
  stuck startup can never trap you.
- Settings: Dark mode / Normal (light) mode switch (applies instantly, no
  restart; HUD and startup screen stay dark), "Speak replies aloud" toggle,
  "Keep dashboard above other windows" toggle, and the settings dialog now
  scrolls. Preferences are saved in data/user_prefs.json.
- Auto-delete __pycache__: on by default. Every launch sweeps all
  __pycache__ folders (skipping venv) and tells Python not to recreate
  them. Toggle off or "Clear now" in Settings -> Maintenance.
- Settings -> "AI, email & voice": change the AI provider, API key and model;
  the email account EV.AI sends from (Outlook / Gmail / other SMTP — your
  Outlook ID and app password); wake word and speech engine/voice. Saved
  into .env without touching your other lines, with an offer to restart.
  Secrets are never shown back, and blank means "keep what's saved".
- Settings: Observe-mode check interval (10s-2min), "Save conversation…"
  to a text file, and "Open data folder".
- Settings: "Check API key" and "Send a test email to myself" buttons
  (run in the background, so the window never freezes), and an optional
  "Minimize to the system tray when closed" setting (tray icon with
  Show / Quit; EV.AI keeps running while the window is hidden).
- More AI providers: ChatGPT (OpenAI), OpenRouter, DeepSeek, Mistral, xAI
  Grok and "Custom" (any OpenAI-compatible server, e.g. Ollama/LM Studio via
  a server address) alongside Claude, Gemini and Groq. Pick them in
  Settings -> AI, email & voice. Needs `pip install -r requirements.txt`
  (adds the `openai` package).
- Email: spaces in app passwords are ignored (Gmail shows them in groups), and a rejected login now shows the mail server's actual reply with a specific hint.
- EV icon: the window, taskbar and tray now use the EV logo instead of the
  Python one (assets/icons/ev.ico), and Windows treats EV as its own app
  (not "pythonw"). Settings -> Maintenance -> "Create EV shortcut" makes an
  "EV" shortcut (app folder + Start menu) you can right-click -> Pin to taskbar.
- Contacts: say "save Mom's email as mom@example.com", then "email Mom".
  Addresses you send to are remembered automatically. Stored in
  data/contacts.json. New tools: save_contact, list_contacts.
- Inbox: ask "do I have new email?" — EV lists the newest messages (sender,
  subject, date only; read-only, nothing is marked as read). New tool: check_email.
- Settings: "Start hidden in the tray" (use with minimize-to-tray).
- Fix: "Create EV shortcut" failed with a PowerShell quoting error; paths are now passed safely.
- "Summarize this email": EV reads one message on request (latest, a number
  from the list, or by sender/subject) and summarises it. Read-only; the text
  is length-capped. New tool: read_email.
- Global hotkey Ctrl+Alt+E shows/hides EV from any app (Settings -> Behaviour
  to turn off; if another program already uses it, EV just goes without).
- Morning briefing: ask "brief me" / "good morning" for date, unread mail,
  pending timers and scheduled tasks. Optional "Read a morning briefing when EV
  opens" in Settings. New tool: morning_briefing; timers are now listable.
- Video mode and Song mode are back as buttons under Observe in the left panel.
  Video = webcam hand-gesture control (as before; still toggleable from the HUD).
  Song = a small floating music remote: type a song/artist -> Play opens it on
  YouTube; buttons for previous / play-pause / next, volume and mute (system media keys).
- More gestures (Video mode): thumbs up / thumbs down = volume up / down
  (repeats while held), pointing finger = previous track, three fingers =
  screenshot snip (Win+Shift+S), rock sign = Windows search (Win+S), open-hand
  swipe up = Task View, swipe down = show desktop. Pinch-zoom is paused while
  these poses are held so they can't zoom by accident.
- Reminders, to-dos and notes now persist (data/personal.json): reminders set
  for later still fire after EV is closed and reopened (missed ones are
  announced on start). New voice/AI tools: set_reminder_at, list_reminders,
  cancel_reminder, add_todo, list_todos, complete_todo, remove_todo, add_note,
  list_notes, delete_note. "What should I do next?" uses your to-do list, and
  the morning briefing now includes open to-dos.
- Privacy center (Settings -> Open privacy center): live microphone / camera /
  screen status, connected services, what is stored on this PC, which actions
  always ask first, and a history of every action EV has taken
  (data/automation_history.jsonl; secrets masked, email bodies never stored).
- Offline mode: when the AI can't be reached (no internet / no key) EV still
  handles the basics itself — open apps, timers and "remind me in 5 minutes to…",
  volume and media keys, the time and date, simple maths ("what is 12 times 5"),
  to-dos and notes. Optional "Handle simple commands without the AI" in Settings
  uses it first, for speed.
- Image help: the 📎 button next to the command box (or drag an image into the
  window) lets you share a picture, screenshot or diagram and ask about it —
  "explain this", "what does this error mean", "read the text", "help with
  this homework/circuit". Paste a Win+Shift+S snip via "Paste image from
  clipboard". Images are resized, sent once to your AI provider, and never saved.
- Settings additions: "Play a soft sound when hovering buttons" switch;
  Profiles (Default / Study / Gaming / Work — each sets a bundle of switches
  and EV's mode in one click); search box at the top of Settings ("voice",
  "API", "theme"…); theme live preview (Keep / Undo — closing without Keep
  undoes it) and "Preview this voice" in account settings (hear a voice
  before saving); new System & About section — version, Check for updates
  (set UPDATE_CHECK_URL in .env), Diagnostics & logs (copyable, secret-free),
  Export / Import settings, Reset settings to defaults. App version is now 1.0.0.
- Release tooling: scripts/make_release.py builds a clean release zip (code only — never your .env, data/, database/ or venv/) plus version.json for "Check for updates", and refuses to build if it finds anything that looks like an API key. Added README.md, LICENSE (MIT — put your name in it) and a stricter .gitignore.
- Self-update: Settings -> Check for updates now installs updates by itself.
  It reads version.json, shows what's new, and on "Yes" downloads the release
  zip, verifies its SHA-256 checksum (https only), backs up the files it is about
  to replace (data/update_backup/), installs only whitelisted code files (never
  .env, data/, database/ or venv/), installs new packages if requirements.txt
  changed, and offers to restart. Any failure rolls back automatically.
  Optional quiet check when EV opens ("Tell me when an update is available").
  scripts/make_release.py now writes zip_url + sha256 into version.json
  (--base-url). Put your version.json address in config.py
  (DEFAULT_UPDATE_CHECK_URL) before publishing so every copy checks it.
- Startup animation: when the loading screen completes, the green geometry
  in the centre expands across the screen, then shrinks into the main window
  as the dark veil fades out. Skipped automatically if EV starts hidden in
  the tray or anything goes wrong.
- Release workflow: version number and release notes now live in app_version.py (bump VERSION there, not in config.py), so updates never overwrite your update-check address in config.py. RELEASE_NOTES.md added; version is 1.0.1.
- Camera fix: closing the window to the tray now turns Video mode off so the
  webcam is freed (the Windows Camera app no longer says "another app is using
  the camera"). New tray menu item "Release camera" frees it any time.
- Startup animation diagnostics: errors are logged to data/animation_error.log; scripts/test_animation.py plays the animation standalone. Version 1.0.3.
- WhatsApp: runs on one dedicated thread (fixes cross-thread Playwright errors), multiple fallback selectors, case-insensitive/partial contact match, send verification, debug screenshot in data/ on failure. Version 1.0.4.
- Fixed the startup animation crash (QPainter.drawEllipse called with a stray argument). Version 1.0.5.
- New logo: assets/icons/ev.ico, ev_icon.png, ev_logo.png. Startup animation (ui/transition.py) now uses the logo: full-screen, slow shrink into the main window's core. New ui/video_view.py: Video mode camera window with HUD rings + hand-tracking reticle (gesture worker now emits a clean frame and the index-finger position). Version 1.0.6.
- v1.0.7: in-app logo->core morph intro; Video mode HUD tracks the eye (face detection in gesture worker), small/shrinkable/resizable camera window; compact corner HUD for other modes (no backdrop dim, left video panel hidden, 🎥 button in HUD header, shrink button); Song panel shrink; 8 colour themes built from dark_theme.qss (ui/theme.py), AI core + video HUD follow the theme colours.
- Release 1.0.3 rolls up the interim 1.0.2-1.0.7 builds (camera release fix, WhatsApp reliability, new logo, in-app intro, eye-tracking Video HUD, compact HUD, 8 themes). Version number is 1.0.3.
- Intro animation: own frame clock (never skips when the window is busy), console messages, Settings > Replay intro animation; startup worker waits for itself to finish before terminate(). Build 25.

## 1.0.4 (build 27) — New gesture control
- Video mode now uses a two-hand gesture system (core/gesture_engine.py): zoom, tab switch, virtual-desktop switch, volume, Win+1/2/3, pause/resume. Replaces the old pinch/pose gestures.
- Settings -> Gesture control: plain-language guide, on/off switch, resume option, adjustable thresholds and cooldowns (applied live), reset button.
- Camera window shows camera/gesture state (on / paused / off / error) and the gesture being seen.
- scripts/test_gestures.py checks the rules without a camera.

## 1.0.6 (build 34) — Quick Actions, personalities, personalization, clipboard assistant, Error Doctor
- ui/quick_actions.py: manage saved task chains from a window (app / site / key / type steps).
- core/personality.py: Professional / Friendly / Humorous reply styles, read on every request.
- ui/theme.py: custom theme colours, text-size scaling; window opacity; saved looks (presets).
- tools/clipboard.py: read_clipboard / write_clipboard AI tools.
- core/error_doctor.py + ui/error_doctor_dialog.py: environment checks and known-error advice.
- Focus Mode replaces Study mode (STUDY button removed; the quiet corner mode is now called Focus). core/focus_match.py + ui/focus_mode.py block browser tabs and desktop apps by name; scripts/test_focus.py shows what Focus Mode sees.
- Personality voices: core/voices.py gives Professional / Friendly / Humorous their own Edge neural voice, rate and pitch (falls back to the offline voice with a matching male/female pick). edge_tts_backend gained a pitch option.
- App Usage Insights: core/app_usage.py (local SQLite, foreground-app time, categories), ui/usage_tracker.py, ui/insights_dialog.py, get_usage_summary tool.
- AI File Finder: core/file_finder.py (name index + plain-language filters), ui/file_finder_dialog.py, search_files / open_search_result tools. Programs and scripts are never launched from search.
- Sending email / WhatsApp no longer asks for confirmation by default (setting: confirm_before_sending in Settings -> Behaviour).
- Jarvis Pro (merged from Grok's draft): Mode.JARVIS, get_system_status, read_screen / get_active_window_title / list_recent_screenshots (screenshots auto-pruned to the newest 20), custom macros (whole-phrase match only).
- Switch to Jarvis button above the AI core: gold core, JARVIS MODULES / JARVIS COMMANDS panels replace MODE / QUICK ACTIONS, Jarvis personality prompt; remembered across restarts (pref jarvis_ui). Jarvis is no longer a full-screen HUD mode.
- Jarvis is now system-monitoring only: live monitor panel (ui/system_monitor.py), new tools get_top_processes / get_disk_usage / get_battery_status / check_network / check_system_health, spoken warnings (core/sysmon.py), brain only offers Jarvis the monitoring tools while Jarvis is on. EV's own features removed from the Jarvis panels.
- Startup hand-off animation turns gold (with a warm veil) when Jarvis was on at last exit.
- Connected device (core/devices.py, Settings -> Connected device): pair with a phone via a device code (encodes the number + check character), ring it in-app over the internet (ntfy push, no SIM or Twilio) when the PC shuts down / EV closes while a request is still running. scripts/make_device_code.py and scripts/test_devices.py added.
- 1.0.7: standalone Windows build (EV_AI.spec, .github/workflows/build-windows.yml) with in-app auto-update for the packaged app (core/updater.py stage_frozen + apply_update.bat); Settings -> Startup face check -> Face recognition setup (in-app enrolment) and a startup-check on/off button; new violet EV theme (dark_theme.qss) and a separate Jarvis console look (ui/jarvis_style.py); compact no-scroll left panel with a 2-column tools grid.
- 1.0.8: Error Doctor understands the standalone app (bundled packages are checked with find_spec, venv/pip advice replaced).
