"""
tools/automation.py
----------------------
Stage 8 AI-facing tools: save/list/delete task chains, and
schedule/list/cancel recurring tasks. Storage only — same pattern as
tools/memory.py. Steps and tool_args travel as JSON-encoded strings
rather than nested objects/arrays, because not every AI provider's
tool-calling schema here supports nested array/object parameters
cleanly (core/brain.py's Gemini conversion in particular); a JSON
string parameter works identically across all three providers.

Running a saved chain's steps needs a live ToolRouter to dispatch each
one, so that part is implemented as a method on ToolRouter itself (see
core/router.py's run_task_chain tool registration) rather than here.
"""

import json

from core.automation import AutomationStore

_store: AutomationStore | None = None


def get_store() -> AutomationStore:
    global _store
    if _store is None:
        _store = AutomationStore()
    return _store


def _parse_steps(steps_json: str) -> list | dict:
    """Returns the parsed step list, or a dict with an 'error' key."""
    try:
        steps = json.loads(steps_json)
    except (TypeError, ValueError) as e:
        return {"error": f"steps_json must be valid JSON: {e}"}
    if not isinstance(steps, list):
        return {"error": "steps_json must be a JSON array of {\"tool\": ..., \"arguments\": {...}} objects."}
    return steps


def save_task_chain(name: str, steps_json: str) -> dict:
    """Save a named sequence of tool calls to run later as one unit.
    steps_json is a JSON array like:
    '[{"tool": "open_application", "arguments": {"app_name": "chrome"}},
      {"tool": "open_website", "arguments": {"target": "gmail"}}]'
    """
    steps = _parse_steps(steps_json)
    if isinstance(steps, dict):  # parse error
        return steps
    return get_store().save_chain(name, steps)


def list_task_chains() -> dict:
    """List all saved task chains."""
    return get_store().list_chains()


def delete_task_chain(name: str) -> dict:
    """Delete a saved task chain by name."""
    return get_store().delete_chain(name)


def schedule_recurring(message: str, time_of_day: str, weekday: str = "",
                        tool_name: str = "", tool_args_json: str = "") -> dict:
    """Schedule a recurring announcement, optionally paired with a tool
    call, that persists across restarts. time_of_day is 24-hour 'HH:MM'.
    Leave weekday empty for a daily task, or give a day name (e.g.
    'monday') for a weekly one. tool_args_json, if given, must be a JSON
    object string like '{"app_name": "chrome"}'."""
    tool_args = {}
    if tool_args_json:
        try:
            tool_args = json.loads(tool_args_json)
        except (TypeError, ValueError) as e:
            return {"error": f"tool_args_json must be valid JSON: {e}"}
        if not isinstance(tool_args, dict):
            return {"error": "tool_args_json must be a JSON object."}
    return get_store().schedule_recurring(message, time_of_day, weekday, tool_name, tool_args)


def list_scheduled_tasks() -> dict:
    """List all recurring scheduled tasks."""
    return get_store().list_scheduled()


def cancel_scheduled_task(task_id: int) -> dict:
    """Cancel/delete a recurring scheduled task by its id."""
    return get_store().cancel_scheduled(task_id)
