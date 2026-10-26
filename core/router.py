"""
core/router.py
----------------
The tool router — a registry of tools the AI brain can call, plus the
dispatch logic that actually runs them.

Each Tool carries:
  - name / description — what the AI sees, to decide when to use it
  - parameters / required — a JSON-schema-style parameter spec, converted
    to each provider's own tool-calling format inside core/brain.py
  - func — the actual Python callable that does the work (lives in
    tools/*.py, never in this file — this file only routes)
  - requires_confirmation — sensitive tools (arriving in Stage 5, e.g.
    deleting a file) will set this True. The confirmation UI itself is
    a Stage 5/9 concern; this flag just exists now so adding it later
    doesn't mean redesigning the router.

No Qt/UI code and no AI-provider-specific code lives here — that
separation is what lets Stage 5/6 register many more tools without
touching core/brain.py's tool-calling logic, and lets brain.py support
a new AI provider later without touching any tool implementation.
"""

from dataclasses import dataclass, field
from typing import Callable, Any

from tools import system as system_tools
from tools import clipboard as clipboard_tools
from tools import finder as finder_tools
from tools import usage as usage_tools
from tools import applications as app_tools
from tools import files as file_tools
from tools import media as media_tools
from tools import reminders as reminder_tools
from tools import browser as browser_tools
from tools import memory as memory_tools
from tools import automation as automation_tools
from tools import mailer as mailer_tools
from tools import contacts as contact_tools
from tools import briefing as briefing_tools
from tools import tasks as task_tools
from core import audit_log
from tools import documents as document_tools
from tools import whatsapp as whatsapp_tools
from tools import input_control as input_tools
from tools import web_browser as web_browser_tools
from tools import screen as screen_tools
from tools import macros as macro_tools


class ToolError(Exception):
    """Raised when a tool fails to run. Callers (core/brain.py) catch
    this and feed the error back to the model as a tool result, rather
    than crashing the conversation."""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict            # {param_name: {"type": "string", "description": "..."}}
    required: list = field(default_factory=list)
    func: Callable[..., Any] = None
    requires_confirmation: bool = False


class ToolRouter:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        self.register(Tool(
            name="get_system_info",
            description="Get the computer's OS, current CPU usage percent, current RAM usage percent, and disk usage percent.",
            parameters={},
            func=system_tools.get_system_info,
        ))
        self.register(Tool(
            name="get_system_status",
            description=("Full systems check for Jarvis Pro: CPU, RAM, disk, battery, network, "
                         "uptime and top processes. Use for 'status report', 'systems check', "
                         "'how is the PC', 'battery level', 'is the internet up'."),
            parameters={},
            func=system_tools.get_system_status,
        ))
        self.register(Tool(
            name="get_top_processes",
            description=("The apps/processes using the most CPU and memory right now. Use for "
                         "'what is slowing my PC', 'what's using my CPU', 'top processes'."),
            parameters={"limit": {"type": "integer", "description": "How many to list (default 8)."}},
            func=system_tools.get_top_processes,
        ))
        self.register(Tool(
            name="get_disk_usage",
            description="Used and free space on every drive. Use for 'disk space', 'how full is my C drive'.",
            parameters={},
            func=system_tools.get_disk_usage,
        ))
        self.register(Tool(
            name="get_battery_status",
            description="Battery percentage, whether plugged in, and minutes left.",
            parameters={},
            func=system_tools.get_battery_status,
        ))
        self.register(Tool(
            name="check_network",
            description="Check the network connection and whether the internet is reachable.",
            parameters={},
            func=system_tools.check_network,
        ))
        self.register(Tool(
            name="check_system_health",
            description=("One-call health check that lists anything needing attention (high CPU or "
                         "memory, full disk, low battery). Use for 'health check', 'is everything ok'."),
            parameters={},
            func=system_tools.check_system_health,
        ))
        self.register(Tool(
            name="read_screen",
            description=("Capture the primary screen and extract visible text (OCR). "
                         "Use when the user asks what is on screen, to read an error message, "
                         "summarise a page, or answer questions about text currently displayed."),
            parameters={
                "region": {
                    "type": "string",
                    "description": "Capture region: 'screen' (default).",
                },
            },
            func=screen_tools.read_screen,
        ))
        self.register(Tool(
            name="get_active_window_title",
            description="Get the title of the window currently in the foreground.",
            parameters={},
            func=screen_tools.get_active_window_title,
        ))
        self.register(Tool(
            name="list_recent_screenshots",
            description="List the most recent screenshots EV has captured for OCR/vision.",
            parameters={
                "limit": {"type": "integer", "description": "How many to list (default 5, max 20)."},
            },
            func=screen_tools.list_recent_screenshots,
        ))
        self.register(Tool(
            name="list_macros",
            description="List all saved custom voice/text macros (trigger phrases and their actions).",
            parameters={},
            func=macro_tools.list_macros,
        ))
        self.register(Tool(
            name="add_macro",
            description=("Save a custom macro: a short trigger phrase the user can say later, "
                         "and the action/instruction EV should treat it as. Example trigger "
                         "'movie night' → action 'set volume to 40, open Netflix, dim lights note'."),
            parameters={
                "trigger": {"type": "string", "description": "Short phrase the user will say."},
                "action": {"type": "string", "description": "What EV should do or treat as the real request."},
            },
            required=["trigger", "action"],
            func=macro_tools.add_macro,
        ))
        self.register(Tool(
            name="remove_macro",
            description="Delete a saved macro by its trigger phrase.",
            parameters={
                "trigger": {"type": "string", "description": "The trigger phrase to remove."},
            },
            required=["trigger"],
            func=macro_tools.remove_macro,
        ))
        self.register(Tool(
            name="get_datetime",
            description="Get the current date, time, and day of the week.",
            parameters={},
            func=system_tools.get_datetime,
        ))

        # --- App usage insights + file finder ---
        self.register(Tool(
            name="get_usage_summary",
            description=("How much time the user spent in each application (the window in front), top apps and "
                         "category totals (Coding, Study, Browsing, Entertainment). Use for 'how much time did I "
                         "spend coding today', 'which app did I use most', 'my screen time this week'."),
            parameters={
                "period": {"type": "string", "description": "today, yesterday, week or month (default today)."},
                "category": {"type": "string", "description": "Optional: Coding, Study, Browsing or Entertainment."},
            },
            func=usage_tools.get_usage_summary,
        ))
        self.register(Tool(
            name="search_files",
            description=("Search the user's computer by file NAME using a plain-language description, e.g. 'my EV AI "
                         "python file', 'presentation I edited recently', 'images in Downloads', 'Arduino projects'. "
                         "Prefer this over find_files. Returns numbered results with folder and modified date."),
            parameters={
                "query": {"type": "string", "description": "What to find, in the user's own words."},
                "file_types": {"type": "string", "description": "Optional extensions, comma separated, e.g. 'pdf,docx'."},
                "folder": {"type": "string", "description": "Optional folder name, e.g. 'downloads' or 'documents'."},
                "days": {"type": "integer", "description": "Optional: only files changed within this many days."},
            },
            required=["query"],
            func=finder_tools.search_files,
        ))
        self.register(Tool(
            name="open_search_result",
            description=("Open result number N from the latest search_files (e.g. 'open the second result'). "
                         "Say which file you opened. Set show_in_folder to reveal it in File Explorer instead."),
            parameters={
                "number": {"type": "integer", "description": "The result number from the latest search."},
                "show_in_folder": {"type": "boolean", "description": "True to show it in its folder instead of opening."},
            },
            required=["number"],
            func=finder_tools.open_search_result,
        ))

        # --- Clipboard assistant ---
        self.register(Tool(
            name="read_clipboard",
            description=("Read the text the user last copied to the clipboard. Use when they say things like "
                         "'summarize / explain / rewrite / translate what I copied' or 'my clipboard'."),
            parameters={},
            func=clipboard_tools.read_clipboard,
        ))
        self.register(Tool(
            name="write_clipboard",
            description=("Put text on the clipboard so the user can paste it, e.g. a rewritten or summarized version. "
                         "Only use after the user asked for a result they can paste."),
            parameters={"text": {"type": "string", "description": "The text to place on the clipboard."}},
            required=["text"],
            func=clipboard_tools.write_clipboard,
        ))

        # --- Applications ---
        self.register(Tool(
            name="open_application",
            description="Open/launch a desktop application by name, e.g. 'notepad', 'chrome', 'calculator'.",
            parameters={"app_name": {"type": "string", "description": "Name of the application to open."}},
            required=["app_name"],
            func=app_tools.open_application,
        ))
        self.register(Tool(
            name="close_application",
            description=(
                "Close a running application by name. This can lose the user's unsaved work, so "
                "ALWAYS ask the user to confirm in plain conversation before calling this tool. "
                "Only pass confirmed=true after the user has explicitly agreed in a previous message."
            ),
            parameters={
                "app_name": {"type": "string", "description": "Name of the application to close."},
                "confirmed": {"type": "boolean", "description": "True only after the user has explicitly confirmed."},
            },
            required=["app_name"],
            func=app_tools.close_application,
            requires_confirmation=True,
        ))

        # --- Files & folders ---
        self.register(Tool(
            name="open_folder",
            description="Open a folder in File Explorer. Accepts shortcuts like 'downloads', 'desktop', 'documents', or a full path.",
            parameters={"path": {"type": "string", "description": "Folder path or shortcut name to open."}},
            required=["path"],
            func=file_tools.open_folder,
        ))
        self.register(Tool(
            name="create_folder",
            description="Create a new folder at the given path, including any missing parent folders.",
            parameters={"path": {"type": "string", "description": "Full path of the folder to create."}},
            required=["path"],
            func=file_tools.create_folder,
        ))
        self.register(Tool(
            name="find_files",
            description="Search for files whose name contains given text, starting from a folder (defaults to the user's home folder). Returns up to 20 matches.",
            parameters={
                "name": {"type": "string", "description": "Text to search for in file names."},
                "search_path": {"type": "string", "description": "Folder to search in — a shortcut like 'downloads' or a full path. Defaults to the home folder."},
            },
            required=["name"],
            func=file_tools.find_files,
        ))
        self.register(Tool(
            name="read_text_file",
            description="Read the contents of a plain text file (not for binaries, PDFs, or images).",
            parameters={"path": {"type": "string", "description": "Full path of the text file to read."}},
            required=["path"],
            func=file_tools.read_text_file,
        ))
        self.register(Tool(
            name="list_folder",
            description="List the immediate contents (files and subfolders) of a folder. Accepts shortcuts like 'downloads', or a full path.",
            parameters={"path": {"type": "string", "description": "Folder path or shortcut name to list. Defaults to the home folder."}},
            func=file_tools.list_folder,
        ))
        self.register(Tool(
            name="move_file",
            description="Move (or rename, if the destination is a new name in the same folder) a file or folder.",
            parameters={
                "src": {"type": "string", "description": "Path of the file/folder to move."},
                "dst": {"type": "string", "description": "Destination path, or a destination folder to move into."},
            },
            required=["src", "dst"],
            func=file_tools.move_file,
        ))
        self.register(Tool(
            name="copy_file",
            description="Copy a file or folder to a new location, leaving the original in place.",
            parameters={
                "src": {"type": "string", "description": "Path of the file/folder to copy."},
                "dst": {"type": "string", "description": "Destination path, or a destination folder to copy into."},
            },
            required=["src", "dst"],
            func=file_tools.copy_file,
        ))
        self.register(Tool(
            name="rename_file",
            description="Rename a file or folder in place (stays in the same parent folder).",
            parameters={
                "path": {"type": "string", "description": "Path of the file/folder to rename."},
                "new_name": {"type": "string", "description": "The new name (not a full path)."},
            },
            required=["path", "new_name"],
            func=file_tools.rename_file,
        ))
        self.register(Tool(
            name="delete_file",
            description=(
                "Permanently delete a file or folder (folders are removed with their full contents). "
                "This is irreversible — ALWAYS ask the user to confirm in plain conversation before "
                "calling this tool. Only pass confirmed=true after the user has explicitly agreed."
            ),
            parameters={
                "path": {"type": "string", "description": "Path of the file/folder to delete."},
                "confirmed": {"type": "boolean", "description": "True only after the user has explicitly confirmed."},
            },
            required=["path"],
            func=file_tools.delete_file,
            requires_confirmation=True,
        ))

        # --- Media ---
        self.register(Tool(
            name="media_play_pause",
            description="Toggle play/pause on whatever media is currently active.",
            parameters={},
            func=media_tools.play_pause,
        ))
        self.register(Tool(
            name="media_next_track",
            description="Skip to the next track.",
            parameters={},
            func=media_tools.next_track,
        ))
        self.register(Tool(
            name="media_previous_track",
            description="Go back to the previous track.",
            parameters={},
            func=media_tools.previous_track,
        ))
        self.register(Tool(
            name="media_volume_up",
            description="Increase system volume by one step.",
            parameters={},
            func=media_tools.volume_up,
        ))
        self.register(Tool(
            name="media_volume_down",
            description="Decrease system volume by one step.",
            parameters={},
            func=media_tools.volume_down,
        ))
        self.register(Tool(
            name="media_mute",
            description="Toggle mute on system audio.",
            parameters={},
            func=media_tools.mute,
        ))

        # --- Timers / reminders ---
        self.register(Tool(
            name="set_timer",
            description="Set a one-off timer/reminder. After the given number of seconds, EV will announce the message out loud.",
            parameters={
                "seconds": {"type": "integer", "description": "How many seconds from now to fire the timer."},
                "message": {"type": "string", "description": "What EV should say when the timer goes off."},
            },
            required=["seconds"],
            func=reminder_tools.set_timer,
        ))
        self.register(Tool(
            name="set_reminder_at",
            description=("Set a reminder for a specific clock time (kept even if EV is closed and reopened). "
                         "Use get_datetime first if you need today's date."),
            parameters={
                "at": {"type": "string", "description": "'YYYY-MM-DD HH:MM' (24-hour, local) or 'HH:MM' for today/tomorrow."},
                "message": {"type": "string", "description": "What EV should say."},
            },
            required=["at", "message"],
            func=reminder_tools.set_reminder_at,
        ))
        self.register(Tool(
            name="list_reminders",
            description="List pending timers/reminders and when they fire.",
            parameters={},
            func=reminder_tools.list_timers,
        ))
        self.register(Tool(
            name="cancel_reminder",
            description="Cancel a pending timer/reminder by its id (see list_reminders).",
            parameters={"reminder_id": {"type": "integer", "description": "The id from list_reminders."}},
            required=["reminder_id"],
            func=reminder_tools.cancel_timer,
        ))

        # --- To-do list and notes (saved between runs) ---
        self.register(Tool(
            name="add_todo", description="Add an item to the user's to-do list.",
            parameters={"text": {"type": "string", "description": "The task."}},
            required=["text"], func=task_tools.add_todo,
        ))
        self.register(Tool(
            name="list_todos",
            description="Show the to-do list (open items by default). Use this to answer 'what should I do next?'.",
            parameters={"include_done": {"type": "boolean", "description": "Also show finished items."}},
            func=task_tools.list_todos,
        ))
        self.register(Tool(
            name="complete_todo", description="Mark a to-do done, by its number or words from its text.",
            parameters={"which": {"type": "string", "description": "Item number or words from it."}},
            required=["which"], func=task_tools.complete_todo,
        ))
        self.register(Tool(
            name="remove_todo", description="Delete a to-do, by its number or words from its text.",
            parameters={"which": {"type": "string", "description": "Item number or words from it."}},
            required=["which"], func=task_tools.remove_todo,
        ))
        self.register(Tool(
            name="add_note", description="Save a quick note for the user.",
            parameters={"text": {"type": "string", "description": "The note."}},
            required=["text"], func=task_tools.add_note,
        ))
        self.register(Tool(
            name="list_notes", description="Show the user's most recent saved notes.",
            parameters={"limit": {"type": "integer", "description": "How many (default 10)."}},
            func=task_tools.list_notes,
        ))
        self.register(Tool(
            name="delete_note", description="Delete a saved note, by its number or words from it.",
            parameters={"which": {"type": "string", "description": "Note number or words from it."}},
            required=["which"], func=task_tools.delete_note,
        ))

        # --- Web / browser ---
        self.register(Tool(
            name="open_website",
            description="Open a website in the default browser. Accepts a full URL, a bare domain, a known site name (youtube, gmail, github, netflix, etc.), or a saved bookmark name.",
            parameters={"target": {"type": "string", "description": "URL, domain, site name, or bookmark name to open."}},
            required=["target"],
            func=browser_tools.open_website,
        ))
        self.register(Tool(
            name="search_web",
            description="Search the web for a query and open the results in the default browser.",
            parameters={"query": {"type": "string", "description": "What to search for."}},
            required=["query"],
            func=browser_tools.search_web,
        ))
        self.register(Tool(
            name="open_youtube",
            description="Open YouTube's homepage in the default browser.",
            parameters={},
            func=browser_tools.open_youtube,
        ))
        self.register(Tool(
            name="search_youtube",
            description="Search YouTube for a query and open the results in the default browser.",
            parameters={"query": {"type": "string", "description": "What to search for on YouTube."}},
            required=["query"],
            func=browser_tools.search_youtube,
        ))
        self.register(Tool(
            name="open_whatsapp_web",
            description=(
                "Open WhatsApp Web as a page in the user's regular default browser (e.g. Edge), for the "
                "user to look at or use by hand. This does NOT type or send anything and cannot actually "
                "send a message — if the user wants a message sent to someone, use send_whatsapp_message "
                "instead, never this tool."
            ),
            parameters={},
            func=browser_tools.open_whatsapp_web,
        ))
        self.register(Tool(
            name="add_bookmark",
            description="Save a website as a bookmark under a short name, so it can be opened by that name later. Persists across restarts.",
            parameters={
                "name": {"type": "string", "description": "Short name to save this bookmark under."},
                "url": {"type": "string", "description": "The URL to save."},
            },
            required=["name", "url"],
            func=browser_tools.add_bookmark,
        ))
        self.register(Tool(
            name="list_bookmarks",
            description="List all saved bookmarks.",
            parameters={},
            func=browser_tools.list_bookmarks,
        ))

        # --- Memory ---
        self.register(Tool(
            name="remember",
            description=(
                "Save a durable fact for later — a user preference, project info, or a custom "
                "command. category must be one of: preference, project, command, fact. "
                "Refuses to store anything that looks like a password, API key, or credential."
            ),
            parameters={
                "category": {"type": "string", "description": "One of: preference, project, command, fact."},
                "key": {"type": "string", "description": "Short label for this fact, e.g. 'main project'."},
                "value": {"type": "string", "description": "The fact itself, e.g. 'SOS BeaconTap'."},
            },
            required=["category", "key", "value"],
            func=memory_tools.remember,
        ))
        self.register(Tool(
            name="recall",
            description="Look up previously remembered facts, optionally filtered by category and/or a search term.",
            parameters={
                "category": {"type": "string", "description": "Optional: one of preference, project, command, fact."},
                "key": {"type": "string", "description": "Optional: search term to match against remembered keys."},
            },
            func=memory_tools.recall,
        ))
        self.register(Tool(
            name="forget",
            description="Delete one specific remembered fact by its key.",
            parameters={
                "key": {"type": "string", "description": "The key of the fact to delete."},
                "category": {"type": "string", "description": "Optional: narrow to one category."},
            },
            required=["key"],
            func=memory_tools.forget,
        ))
        self.register(Tool(
            name="clear_memory",
            description=(
                "Delete ALL remembered facts, preferences, and project info. This is permanent. "
                "ALWAYS ask the user to confirm in plain conversation before calling this tool. "
                "Only pass confirmed=true after the user has explicitly agreed."
            ),
            parameters={"confirmed": {"type": "boolean", "description": "True only after the user has explicitly confirmed."}},
            func=memory_tools.clear_memory,
            requires_confirmation=True,
        ))
        self.register(Tool(
            name="get_frequent_apps",
            description="List the applications the user opens most often.",
            parameters={"limit": {"type": "integer", "description": "Max number of apps to return. Defaults to 5."}},
            func=memory_tools.get_frequent_apps,
        ))

        # --- Automation: task chains + recurring scheduled tasks ---
        self.register(Tool(
            name="save_task_chain",
            description=(
                "Save a named sequence of tool calls to run later as one unit, e.g. a 'start work' "
                "routine that opens several apps/sites at once. steps_json is a JSON array string "
                "like '[{\"tool\": \"open_application\", \"arguments\": {\"app_name\": \"chrome\"}}, "
                "{\"tool\": \"open_website\", \"arguments\": {\"target\": \"gmail\"}}]' — only use tool "
                "names that actually exist. Do not include confirmed=true for a sensitive step unless "
                "the user has explicitly agreed that this chain should perform it without asking again "
                "each time it runs."
            ),
            parameters={
                "name": {"type": "string", "description": "Short name to save this chain under, e.g. 'start work'."},
                "steps_json": {"type": "string", "description": "JSON array string of {tool, arguments} steps."},
            },
            required=["name", "steps_json"],
            func=automation_tools.save_task_chain,
        ))
        self.register(Tool(
            name="run_task_chain",
            description="Run a previously saved task chain by name, executing each of its steps in order.",
            parameters={"name": {"type": "string", "description": "Name of the saved task chain to run."}},
            required=["name"],
            func=self._run_task_chain,
        ))
        self.register(Tool(
            name="list_task_chains",
            description="List all saved task chains.",
            parameters={},
            func=automation_tools.list_task_chains,
        ))
        self.register(Tool(
            name="delete_task_chain",
            description="Delete a saved task chain by name.",
            parameters={"name": {"type": "string", "description": "Name of the task chain to delete."}},
            required=["name"],
            func=automation_tools.delete_task_chain,
        ))
        self.register(Tool(
            name="schedule_recurring",
            description=(
                "Schedule a recurring announcement (optionally paired with one tool call) that persists "
                "across restarts — e.g. a daily reminder, or a weekly action. time_of_day is 24-hour "
                "'HH:MM'. Leave weekday empty for daily, or give a day name like 'friday' for weekly."
            ),
            parameters={
                "message": {"type": "string", "description": "What EV should say when this fires."},
                "time_of_day": {"type": "string", "description": "24-hour 'HH:MM', e.g. '09:00'."},
                "weekday": {"type": "string", "description": "Optional: a day name for a weekly task. Leave empty for daily."},
                "tool_name": {"type": "string", "description": "Optional: a tool to also run when this fires."},
                "tool_args_json": {"type": "string", "description": "Optional: JSON object string of arguments for tool_name."},
            },
            required=["message", "time_of_day"],
            func=automation_tools.schedule_recurring,
        ))
        self.register(Tool(
            name="list_scheduled_tasks",
            description="List all recurring scheduled tasks.",
            parameters={},
            func=automation_tools.list_scheduled_tasks,
        ))
        self.register(Tool(
            name="cancel_scheduled_task",
            description="Cancel a recurring scheduled task by its id (see list_scheduled_tasks).",
            parameters={"task_id": {"type": "integer", "description": "The id of the scheduled task to cancel."}},
            required=["task_id"],
            func=automation_tools.cancel_scheduled_task,
        ))

        # --- Stage 9: email, real document creation, WhatsApp ---
        self.register(Tool(
            name="send_email",
            description=(
                "Send a real email via the configured account. When the user asks to send an email, "
                "send it right away (write a sensible subject/body from what they said if they didn't "
                "spell it out) and pass confirmed=true. Only ask first if the recipient is unclear. "
                "If the tool returns confirmation_required, the user has turned confirmations on: "
                "relay the message and wait for their yes."
            ),
            parameters={
                "to": {"type": "string", "description": "Recipient's email address, or the name of a saved contact (e.g. \"Mom\")."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Plain-text email body."},
                "confirmed": {"type": "boolean", "description": "Pass true when sending."},
            },
            required=["to", "subject", "body"],
            func=mailer_tools.send_email,
        ))
        self.register(Tool(
            name="check_email",
            description=("Read-only: list the newest emails in the user's inbox (sender, subject, date — "
                         "not the message text). Use for 'do I have new mail' / 'check my email'."),
            parameters={
                "unread_only": {"type": "boolean", "description": "True (default) for unread mail only."},
                "limit": {"type": "integer", "description": "How many to list, 1-15 (default 5)."},
            },
            required=[],
            func=mailer_tools.check_email,
        ))
        self.register(Tool(
            name="read_email",
            description=("Read ONE email's text so it can be summarised (read-only, not marked as read). "
                         "Use for 'summarize my latest email' / 'what did <person> send me'. "
                         "Call check_email first if the user wants to pick from a list."),
            parameters={
                "which": {"type": "string", "description": "'latest' (default), a list position like '2', or words from the sender/subject."},
                "unread_only": {"type": "boolean", "description": "Only consider unread mail."},
            },
            required=[],
            func=mailer_tools.read_email,
        ))
        self.register(Tool(
            name="morning_briefing",
            description=("Gather today's date, unread email headlines, pending timers and scheduled tasks "
                         "for a short spoken briefing. Use for 'good morning' / 'brief me' / 'what's my day look like'."),
            parameters={},
            required=[],
            func=briefing_tools.morning_briefing,
        ))
        self.register(Tool(
            name="save_contact",
            description="Save a person's email address under a name so the user can say 'email <name>' later.",
            parameters={
                "name": {"type": "string", "description": "The contact's name, e.g. Mom."},
                "email": {"type": "string", "description": "Their email address."},
            },
            required=["name", "email"],
            func=contact_tools.save_contact,
        ))
        self.register(Tool(
            name="list_contacts",
            description="List saved email contacts and recently emailed addresses.",
            parameters={},
            required=[],
            func=contact_tools.list_contacts,
        ))
        self.register(Tool(
            name="create_text_document",
            description="Create a plain .txt file with the given content.",
            parameters={
                "path": {"type": "string", "description": "Full path (or folder shortcut + filename) to save to."},
                "content": {"type": "string", "description": "The text content to write."},
                "confirmed": {"type": "boolean", "description": "True only if the user confirmed overwriting an existing file at this path."},
            },
            required=["path", "content"],
            func=document_tools.create_text_document,
            requires_confirmation=True,
        ))
        self.register(Tool(
            name="create_word_document",
            description="Create a real Microsoft Word (.docx) document. Each line of content becomes a paragraph.",
            parameters={
                "path": {"type": "string", "description": "Full path (or folder shortcut + filename) to save to."},
                "content": {"type": "string", "description": "The document's text content, one paragraph per line."},
                "confirmed": {"type": "boolean", "description": "True only if the user confirmed overwriting an existing file at this path."},
            },
            required=["path", "content"],
            func=document_tools.create_word_document,
            requires_confirmation=True,
        ))
        self.register(Tool(
            name="create_pdf_document",
            description="Create a simple PDF file with the given text content.",
            parameters={
                "path": {"type": "string", "description": "Full path (or folder shortcut + filename) to save to."},
                "content": {"type": "string", "description": "The text content to write."},
                "confirmed": {"type": "boolean", "description": "True only if the user confirmed overwriting an existing file at this path."},
            },
            required=["path", "content"],
            func=document_tools.create_pdf_document,
            requires_confirmation=True,
        ))
        self.register(Tool(
            name="create_spreadsheet",
            description=(
                "Create a real Excel (.xlsx) spreadsheet from CSV-formatted data, e.g. "
                "'Name,Age\\nAlice,30\\nBob,25'."
            ),
            parameters={
                "path": {"type": "string", "description": "Full path (or folder shortcut + filename) to save to."},
                "csv_data": {"type": "string", "description": "CSV-formatted rows, including a header row if wanted."},
                "confirmed": {"type": "boolean", "description": "True only if the user confirmed overwriting an existing file at this path."},
            },
            required=["path", "csv_data"],
            func=document_tools.create_spreadsheet,
            requires_confirmation=True,
        ))
        self.register(Tool(
            name="send_whatsapp_message",
            description=(
                "Send a WhatsApp message to a contact via WhatsApp Web browser automation. Slower than "
                "send_email and opens a visible browser window; the first-ever use needs the user to "
                "scan a QR code in that window. When the user asks to message someone, send it right "
                "away with confirmed=true. If the tool returns confirmation_required, the user has "
                "turned confirmations on: relay the message and wait for their yes."
            ),
            parameters={
                "contact": {"type": "string", "description": "Contact name exactly as it appears in the WhatsApp chat list."},
                "message": {"type": "string", "description": "The message to send."},
                "confirmed": {"type": "boolean", "description": "Pass true when sending."},
            },
            required=["contact", "message"],
            func=whatsapp_tools.send_whatsapp_message,
        ))

        # --- Stage 9: live dictation + voice-driven browser control ---
        self.register(Tool(
            name="type_text",
            description=(
                "Type text into whatever window/field currently has keyboard focus, exactly as if "
                "the user typed it themselves — use this for 'type this', dictation-style requests."
            ),
            parameters={"text": {"type": "string", "description": "The text to type."}},
            required=["text"],
            func=input_tools.type_text,
        ))
        self.register(Tool(
            name="press_key",
            description="Press a single key or key combo on the keyboard, e.g. 'enter', 'tab', 'ctrl+a', 'esc'.",
            parameters={"key": {"type": "string", "description": "Key or combo to press, e.g. 'enter' or 'ctrl+s'."}},
            required=["key"],
            func=input_tools.press_key,
        ))
        self.register(Tool(
            name="browser_search_google",
            description="Search Google for a query in a controlled, EV-driven browser window that stays open for further commands (click, scroll, type, etc).",
            parameters={"query": {"type": "string", "description": "What to search for."}},
            required=["query"],
            func=web_browser_tools.browser_search_google,
        ))
        self.register(Tool(
            name="browser_open",
            description="Navigate the controlled browser window to a URL or bare domain.",
            parameters={"url": {"type": "string", "description": "URL or domain to open."}},
            required=["url"],
            func=web_browser_tools.browser_open,
        ))
        self.register(Tool(
            name="browser_click",
            description="Click the first visible link/button/element on the current page whose text contains the given text, e.g. to click a search result.",
            parameters={"text": {"type": "string", "description": "Visible text of the element to click."}},
            required=["text"],
            func=web_browser_tools.browser_click,
        ))
        self.register(Tool(
            name="browser_type",
            description="Type text into whatever input/textbox currently has focus on the current browser page.",
            parameters={"text": {"type": "string", "description": "Text to type into the page."}},
            required=["text"],
            func=web_browser_tools.browser_type,
        ))
        self.register(Tool(
            name="browser_press_enter",
            description="Press Enter on the current browser page, e.g. to submit a search box or form.",
            parameters={},
            func=web_browser_tools.browser_press_enter,
        ))
        self.register(Tool(
            name="browser_scroll",
            description="Scroll the current browser page up or down.",
            parameters={"direction": {"type": "string", "description": "'up' or 'down'. Defaults to 'down'."}},
            func=web_browser_tools.browser_scroll,
        ))
        self.register(Tool(
            name="browser_go_back",
            description="Go back to the previous page in the controlled browser window.",
            parameters={},
            func=web_browser_tools.browser_go_back,
        ))
        self.register(Tool(
            name="close_browser_session",
            description="Close the controlled browser window, if one is open.",
            parameters={},
            func=web_browser_tools.close_browser_session,
        ))

    # ------------------------------------------------------------------
    # Task chain execution — needs self.execute(), so it lives here
    # rather than in tools/automation.py (which only stores definitions,
    # same separation as every other tools/*.py module).
    # ------------------------------------------------------------------
    def _run_task_chain(self, name: str) -> dict:
        steps = automation_tools.get_store().get_chain(name)
        if steps is None:
            return {"error": f"No task chain named '{name}'."}

        results = []
        for step in steps:
            tool_name = step.get("tool")
            arguments = step.get("arguments") or {}
            tool = self.get(tool_name)
            if tool is None:
                results.append({"tool": tool_name, "error": "unknown tool, skipped"})
                continue
            if tool.requires_confirmation and not arguments.get("confirmed"):
                # Never let a saved chain silently perform a confirmation-
                # gated action — this is the same invariant core/modes.py
                # documents for conversational modes: nothing here can
                # override a tool's own confirmation requirement.
                results.append({
                    "tool": tool_name,
                    "skipped": True,
                    "reason": "requires confirmation, not included in the saved chain",
                })
                continue
            try:
                results.append({"tool": tool_name, "result": self.execute(tool_name, arguments)})
            except ToolError as e:
                results.append({"tool": tool_name, "error": str(e)})

        return {"status": "done", "name": name, "steps_run": len(results), "results": results}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def requires_confirmation(self, name: str) -> bool:
        tool = self.get(name)
        return bool(tool and tool.requires_confirmation)

    def execute(self, name: str, arguments: dict) -> dict:
        """Run a tool by name with the given arguments. Always returns a
        JSON-serializable dict — raises ToolError on failure rather than
        letting a raw exception escape, so the brain layer can always
        feed *something* back to the model instead of crashing."""
        tool = self.get(name)
        if tool is None:
            raise ToolError(f"Unknown tool '{name}'.")
        try:
            result = tool.func(**(arguments or {}))
        except TypeError as e:
            audit_log.record(name, arguments, False, "bad arguments")
            raise ToolError(f"Bad arguments for '{name}': {e}") from e
        except Exception as e:
            audit_log.record(name, arguments, False, str(e))
            raise ToolError(f"Tool '{name}' failed: {e}") from e

        if isinstance(result, dict) and result.get("confirmation_required"):
            audit_log.record(name, arguments, True, "asked for confirmation")
        elif isinstance(result, dict) and result.get("error"):
            audit_log.record(name, arguments, False, str(result["error"]))
        else:
            audit_log.record(name, arguments, True)

        if result is None:
            return {"status": "ok"}
        if isinstance(result, dict):
            return result
        return {"result": result}
