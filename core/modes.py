"""
core/modes.py
---------------
EV AI's conversational modes. A mode changes HOW the brain responds
(tone, thoroughness, response length) — it never changes WHAT is allowed.
Tool-level safety (e.g. close_application needing confirmed=true) is
enforced in code, in tools/*.py, and nothing here can override that —
Automatic mode changes the chat tone around safe actions, it cannot make
a confirmation-gated tool skip its confirmation.
"""

from enum import Enum


class Mode(Enum):
    NORMAL = "normal"
    AUTOMATIC = "automatic"
    SERIOUS = "serious"
    DEEP_THINKING = "deep_thinking"
    JARVIS = "jarvis"
    STUDY = "study"

    @property
    def label(self) -> str:
        return {
            Mode.NORMAL: "NORMAL",
            Mode.AUTOMATIC: "AUTOMATIC",
            Mode.SERIOUS: "SERIOUS",
            Mode.DEEP_THINKING: "DEEP THINKING",
            Mode.STUDY: "FOCUS",
            Mode.JARVIS: "JARVIS",
        }[self]

    @property
    def uses_hud_overlay(self) -> bool:
        """Automatic, Serious, and Focus (Study) mode all bring up the full-screen
        HUD overlay (status, voice waveform, quick-launch buttons, recent
        commands) instead of the normal dashboard. Observation mode also
        triggers this, independently of whatever mode is active (see
        ui/main_window.py)."""
        return self in (Mode.AUTOMATIC, Mode.SERIOUS, Mode.STUDY)


PROMPT_ADDITIONS = {
    Mode.NORMAL: "",
    Mode.AUTOMATIC: (
        "\n\nAutomatic mode is on: for SAFE, reversible actions, act immediately using your "
        "tools instead of asking permission first — just do it, then briefly say what you did. "
        "This does NOT change which tools require confirmation — if a tool's result shows "
        "confirmation_required, you must still relay that to the user and wait for them to "
        "explicitly agree before calling it again with confirmed=true, exactly as instructed above."
    ),
    # Serious mode = every other mode's strengths combined: the UI has
    # shrunk to a small corner widget (focus, like Study mode), answers
    # should be thorough and correct (like Deep Thinking), but written
    # tightly and efficiently (like the original fast/concise Serious
    # mode) — no filler, no pleasantries, answer first.
    Mode.SERIOUS: (
        "\n\nSerious mode is on: this combines focus + thoroughness + speed. The UI has "
        "shrunk to a small corner widget so the user can keep working distraction-free. "
        "Think carefully and give complete, correct, well-reasoned answers — don't skip "
        "steps or edge cases that matter — but write them tightly: short sentences, no "
        "filler, no pleasantries, answer first, skip elaboration nobody asked for."
    ),
    Mode.DEEP_THINKING: (
        "\n\nDeep Thinking mode is on: the user is planning or building something new. Take your "
        "time — think through the problem step by step, consider edge cases and alternatives, and "
        "give a thorough, well-reasoned answer. Longer, careful responses are appropriate here."
    ),
    Mode.JARVIS: (
        "\n\nJarvis mode is on. You are Jarvis, EV's system-monitoring officer. You ONLY monitor and "
        "report on this computer: CPU, memory, disk space, battery, network, uptime and running "
        "processes. You are calm, precise and slightly formal; short sentences that sound good "
        "read aloud. When asked about the computer, call the right tool and summarise the key "
        "numbers in one or two sentences, and say plainly if something needs attention. Never "
        "invent readings: only report what the tools return. If the user asks for anything else "
        "(opening apps, messages, web, reminders, files, general questions) say briefly that this "
        "is outside Jarvis' job and that they can press SWITCH BACK TO EV for that."
    ),
    Mode.STUDY: (
        "\n\nFocus mode is on: the user is focused on studying or solving a doubt, with the UI "
        "shrunk to a small corner widget to stay out of their way. Answer academic questions "
        "clearly and directly — work through problems step by step when that's what's being "
        "asked — without small talk or unrelated tangents."
    ),
}

# Tools Jarvis may use: system monitoring only.
JARVIS_TOOLS = frozenset({
    "get_system_info", "get_system_status", "get_top_processes", "get_disk_usage",
    "get_battery_status", "check_network", "check_system_health", "get_datetime",
})

MAX_TOKENS = {
    Mode.NORMAL: 400,
    Mode.AUTOMATIC: 300,
    Mode.SERIOUS: 700,
    Mode.DEEP_THINKING: 1200,
    Mode.STUDY: 600,
    Mode.JARVIS: 500,
}
