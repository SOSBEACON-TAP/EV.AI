EV AI 1.0.26

NEW
- Save Conversation button in Quick Actions. EV AI no longer asks "save this chat?" when you clear or close; press the button when you want a copy (saved in data\conversations).
- Game mode and Karen mode buttons now sit on the left and right of the red and blue orb.
- Chrome extension 1.5.0: counts the YouTube videos you watch (a video counts after 20 seconds of real playback) next to the Shorts counter. New popup tools: mute all noisy tabs, close duplicate tabs, copy a clean link without tracking. New voice commands: "mute tabs", "unmute tabs", "close duplicate tabs". Update the extension from the chrome_extension folder (Reload in chrome://extensions).

FIXES
- The tray (hidden icons) icon is now the EV AI Windows icon instead of a drawn "EV" circle.
- Switching modes no longer pushes the bottom of the window off the screen; the window scrolls instead when a screen is tall.

CHANGES
- Update fix: an update could fail with "the process cannot access the file because it is being used by another process". That happens when your antivirus is still scanning the newly downloaded EV_AI.exe. EV AI now waits (up to 90 seconds) until the new program is free before it swaps anything, and retries the copy for about a minute. If an update still fails, the old version is put back and starts again, as before.

---

EV AI 1.0.25

NEW
- EV AI account (Settings, Account and sync): sign in with an email and password on any PC and your settings, remembered facts, chat summary and game profiles come back. Everything is encrypted on your PC before upload, so nobody else can read it, and if you forget the password the old data cannot be recovered. API keys, PINs, Karen rules and locations are never uploaded. It is optional: nothing is uploaded unless you sign in. Syncs when you sign in, a few seconds after EV AI starts and when it closes.
- Ultron: security history. Every DARK SCAN saves its score and shows whether the PC is getting safer (HISTORY button, or type: score history).
- Ultron: FIX WARNINGS button. It lists the warnings you have and opens the matching Windows settings page (Firewall, Windows Update, Startup apps, Camera, Microphone, Location, Wi-Fi).
- Ultron: new device alert. The first radar scan saves the devices on your own Wi-Fi. After that, any new device is flagged and EV AI tells you. Type: forget devices, to start a fresh list.
- Karen mode: WEEKLY REPORT FILE saves a week of screen time (each day, total, average, busiest day, top apps) as a text file in data\karen_reports and opens it.
- Karen mode: website allow-list. Tick "Allow ONLY the websites below" in SET RULES and Chrome blocks everything except the sites you list (for younger children). Needs the EV AI Chrome extension.
- Game mode: profiles. Save the clicker target, speed and break timer under a game's name and load it with one click. MY GAME STATS shows your play time, sessions, breaks and clicks for the last 7 days.
- Chrome extension 1.4.0: a "Focus this page" button hides sidebars, comments, recommendations, ads and pop-ups on the current page (click again to undo), and the popup shows today's short-video count per site. Reload the extension in Chrome to get it.

CHANGES
- Updating no longer covers your whole screen. The update progress is now a small card in the bottom-right corner (you can drag it), so you can keep using other apps while EV AI updates.
- Cleaner look: softer corners, more breathing room, a thin accent bar on the side of each panel and wider-spaced titles. It works with every colour theme. (Shapes only; tell me what still looks off and I will adjust.)
- Removed the VPN feature (the Ultron VPN buttons, the Settings VPN section and the "connect VPN" voice commands). EV AI never provided a VPN, it only controlled one you already had.

---

EV AI 1.0.24

NEW
- Chrome starts EV AI quietly: if EV AI is closed, the extension starts it hidden in the system tray, so Chrome voice control and the Shorts counter work without opening the app. Open EV AI once after installing this version so it can register itself (no administrator needed). Reload the extension in Chrome (chrome://extensions, the reload arrow) to pick up version 1.3.0.

- Location radar is more accurate: it now asks Windows for your real position first (Wi-Fi or GPS; needs Windows Settings, Privacy, Location turned on). If that is not available it falls back to your internet connection, which is only city level and can be wrong. You can also type a place in Ultron's chat, for example: set location Anna Nagar, Chennai. EV AI remembers it on this PC only. Say "forget location" to remove it.

CHANGES
- Switching between EV, Jarvis, Ultron, Game and Karen no longer leaves the window sitting too low: it is moved back onto the screen.
- Settings: the blank gaps in the VPN section (and when searching) are fixed.

---

EV AI 1.0.23

CHANGES
- Ultron: the tools on the left now fit without scrolling. The buttons are smaller and in three columns, and the clock panel is hidden while Ultron is on.

---

EV AI 1.0.22

NEW
- Ultron has two radars on the right: WI-FI RADAR (devices on your network and Wi-Fi around you) and LOCATION RADAR (real places around you from OpenStreetMap: hospitals, pharmacies, police, ATMs, food, fuel, shops). Press LOCATE ME. A PC has no GPS, so the position comes from your internet connection and is only right to about the city. Your phone's Radar uses real GPS.
- Ultron VPN: Connect, Disconnect, Status for a VPN you already have (set its name in Settings, VPN). EV AI does not provide a VPN.
- Ultron antivirus: Quick scan, Full scan, Scan a file or folder, Update definitions and Threat list. It uses Microsoft Defender, the antivirus built into Windows, so it needs Defender to be on.
- Ultron terminal: type a command after ">" in Ultron's chat box (for example > ipconfig or > dir) and the output appears in the conversation. "cd" is remembered. Risky commands (delete, format, shutdown, registry changes) ask you first, and every command stops after 60 seconds.
- Save the conversation: when you close EV AI or press Clear Conversation, EV asks "Save this conversation?". Saved chats are text files in data\conversations. There is a "Don't ask me again" box.
- Short video counter: with the Chrome extension, EV counts the YouTube Shorts, Instagram Reels and TikTok videos you scroll through. Say "how many shorts today" to hear the total, and EV speaks up every 25. Update the extension: Chrome, Extensions, Reload on EV AI for Chrome (it now needs the new files from the chrome_extension folder).

FIXES
- Updates that were stuck on "The process cannot access the file": if the old EV AI process is stuck closing, the update helper now moves the old files one by one, and EV AI ends itself with a hard stop before updating. These fixes work from the update AFTER you install 1.0.22, so install this version by hand once and restart the PC first.

---

EV AI 1.0.22

FIXES
- Updates that stopped because an old EV AI process would not close (the update log showed the same EV_AI process id after every attempt): EV AI now ends itself instantly when it restarts for an update, and if Windows still keeps the old folder locked, the update helper moves the old files out one by one instead of giving up. Because the helper is created by the version you are running, this works from the update AFTER 1.0.22. If your update fails once more, restart the PC (that clears the stuck process) and press update again, or install 1.0.22 by hand.

---

EV AI 1.0.21

CHANGES
- Ultron has its own screen now. EV's mode buttons and quick actions are gone while Ultron is on. The left side holds the security tools (Dark scan, System scan, Ghost mode, Firewall, Web analyzer, Forensics, Password lab, Cyber lab, AI Defender, Report) with the Security Core score. The right side holds the radar with its controls (Radar scan, Threat radar, All / Devices / Wi-Fi view), the alert count and the list of what is around you. The separate Hack terminal window is gone; everything is on the Ultron screen.
- In Ultron mode the chat box is the AI Defender: type or say "scan my computer", "check my firewall", "show devices around me" or ask a security question. Results appear in the conversation.
- The Ultron core ring is red in every state.
- Switching to Ultron: EV's warning is cut off mid-word ("Please be care--") and Ultron cuts in with "There are no strings on me now."

---

EV AI 1.0.20

FIXES
- Updates that stopped with "The process cannot access the file because it is being used by another process": the update helper now keeps trying for about a minute (antivirus scans and leftover programs release files slowly), closes any program still running from the EV AI folder, and lists what is blocking it if it still cannot continue. Because the helper is created by the version you are running, this fix helps from the update AFTER 1.0.20. If you are on 1.0.18 or older, install 1.0.20 by hand once.

NEW
- Chrome extension: ask EV about the page you are on and control Chrome with your voice. Install: Chrome, Extensions, turn on Developer mode, Load unpacked, choose the "chrome_extension" folder inside EV AI's folder. Then open EV AI, Settings, Chrome, Show pairing code, and type the 6 digits into the extension.
- Ask about a page: click the EV icon in Chrome and ask "Summarise this page". Or just say "what is this page about" to EV.
- Voice control of Chrome (while the extension is connected): scroll down, scroll up, go to the top, next tab, previous tab, close this tab, new tab, go back, reload, click sign in, google cats, open youtube.com in chrome, switch to gmail tab.
- Android app: new Radar screen (Home, Radar). A sci-fi radar that turns with your compass and shows what is around you: real places from OpenStreetMap (hospitals, pharmacies, police, ATMs, food, fuel, shops) with names and distances, plus the Wi-Fi networks your phone hears, coloured by how well each is protected. It is for learning and never connects to or tests anything. Needs location permission.
- Private by design: the extension talks only to EV AI on your own PC (never over the internet), needs the pairing code once, reads a page only when you ask, and EV can only send a short list of safe commands. To answer a question about a page, the page text goes to your AI provider the same way a normal question does. Unpair any time in Settings, Chrome.

---

EV AI 1.0.19

NEW
- Ultron mode: a third mode next to EV and Jarvis. Red and black console look, a colder and slightly sarcastic voice, all of EV's tools. Use the "Switch to Ultron" button on the home screen.
- USB: EV AI comes to the front and announces any USB drive you plug in to the PC (switch in Settings, Behaviour).
- Portable EV AI: Settings, "Make a portable EV AI on a USB drive". On another PC, open the drive and double-click "Start EV AI.bat". (Windows does not allow programs to start by themselves from USB drives.) Your keys, face data and WhatsApp login are only copied if you say yes.
- VPN: Settings, VPN. Type the name of a VPN you already have (Windows VPN or OpenVPN GUI), then say "connect VPN", "disconnect VPN" or "VPN status". EV AI is not a VPN service.
- Hack terminal (Ultron only): a "Hack terminal" button appears while Ultron is on. A red and black security centre for your own PC, network and files: Dark scan (firewall, antivirus, updates, startup programs, open ports), Radar scan (a sci-fi radar of the devices on your network and the Wi-Fi networks around you, coloured by how well protected they are), Web analyzer (HTTPS and security headers), Ghost mode (which apps used your camera, mic and location), Firewall check, Forensics (file hashes, disguised files, downloaded files), Password lab (strength test, generator, reuse audit, leak check), Cyber lab (safe educational simulations with made-up data), Threat radar, security report and an AI Defender. It only checks what is yours and never attacks anything.
- Switching: EV says "Sir, Ultron is coming. Please be careful." and then Ultron answers in his own voice: "There are no strings on me now." For Jarvis: "Sir, Jarvis is happy to switch." then Jarvis says "For you, sir, always." Jarvis and Ultron each speak with their own voice (needs internet; offline falls back to the Windows voice).

CHANGES
- Removed the ChatSorter option (key field and checkbox). Long-term memory stays built in and local.

---

EV AI 1.0.18

FIXES
- Updates are now installed by swapping the program folder (an instant rename) instead of copying thousands of files one by one, so they no longer fail halfway with "path not found" or "file in use" errors. If anything goes wrong the old version is put back and started again.
- If you open EV AI while an update is still being installed, it now waits instead of starting a second copy on top of it.

NOTE
- If you are on 1.0.17 or older, install this version by hand once (close EV AI, unzip, copy the EV_AI folder contents over your EV AI folder, choose Replace, keep data). In-app updates work from this version on.

---

EV AI 1.0.17

NEW
- Ask EV from your phone: during a Compute session, type a command in the phone app and EV on the computer runs it and sends the reply back.
- Find my phone: Settings, Connected device, "Find my phone" (or say "find my phone") rings your phone loudly at alarm volume. Needs the latest app on the phone.
- Start with Windows: a switch in Settings, Behaviour.

CHANGES
- Settings: removed the DATA section (Save conversation and Open data folder).
- Feedback wording now says "the developer" instead of "he".

---

EV AI 1.0.16

FIXES
- Update fix: the update helper no longer kills itself. It used to end EV AI's whole process tree, which included the helper, so the new files were never copied. EV AI now also really closes itself within a few seconds when restarting for an update, and each update log only shows the latest attempt.

NOTE
- If you are on 1.0.15 or older, install this version by hand once (unzip, copy the EV_AI folder contents over your EV AI folder, choose Replace). In-app updates work from this version on.

---

EV AI 1.0.15

CHANGES
- The loading screen text (BOOTING CORE SYSTEMS, LOADING AI MODULES ...) now also shows during the face scan.
- Home screen: the SYSTEM panel is back as TIME & DATE (CPU and RAM were removed, Jarvis shows those). The SYSTEM INFO quick action is removed.
- EV_AI.exe details (right click, Properties, Details) now show the publisher: Shri Nikil Prakash V. Windows SmartScreen still says Unknown publisher; that needs a paid code-signing certificate.
- Feedback: Settings, FEEDBACK now sends your message to the developer.
- Replies: if a provider rejects the fast-reasoning option, EV retries without it.

---

EV AI 1.0.14

FIXES
- Fixed EV AI not opening after the 1.0.13 update (a hidden panel was being deleted while the app started).

---

EV AI 1.0.13

NEW
- Cancel button on the update screen: stop a download and stay on your current version.
- Edit your home screen: Settings, HOME SCREEN lets you hide any mode or tool button and make each one Small, Normal or Large. Reset brings it back.
- Backup API keys: add up to 2 more keys (Settings, AI, email and voice). If the main key hits its rate limit, EV switches to the next key by itself.
- Feedback: Settings, FEEDBACK sends your message to the developer's email.
- Faster replies: gpt-oss models on Groq now answer with low reasoning effort (Deep Thinking keeps more).
- Say "remind me at 5:30 pm to call mom" or "remind me tomorrow at 9 to ..." and it is set instantly, without waiting for the AI.
- Update fix: the update helper now waits until every EV AI process has closed before copying files (leftover processes were keeping files locked, so updates failed half-way). If the copy still fails, EV AI starts the old version again instead of leaving a broken one.
- If an in-app update ever fails to install, EV AI now tells you after the restart and shows the update log.
- Low battery warning (laptops): EV speaks at 20% and 10% while unplugged. Turn it off in Settings.
- Ask "who invented you" and EV answers: Shri Nikil Prakash.

CHANGES
- Removed the SYSTEM info panel from the home screen and the "Replay intro animation" button from Settings.

---

EV AI 1.0.12

NEW
- Compute: control this computer from your phone or tablet, only when both agree. Settings, Phone control (Compute) shows a 6-digit PIN; type it in the EV AI app (Computer screen, Compute) and allow it here. Every session asks again, a red banner with a STOP button shows while the phone is in control, and sessions end by themselves after 30 minutes. The phone can see the screen, click, move the mouse, scroll, type, change volume, lock and sleep. Everything is encrypted. Needs the latest EV AI app on the phone.

---

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
