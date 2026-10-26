"""
core/state.py
--------------
Defines the finite set of states EV AI can be in. The UI observes these
states (via Qt signals — see ui/main_window.py) and changes its appearance
accordingly. Keeping this as a single enum makes state transitions easy to
reason about and prevents "invalid" states from being represented.
"""

from enum import Enum, auto


class AIState(Enum):
    IDLE = auto()          # Waiting for wake word / input, nothing happening
    LISTENING = auto()     # Actively capturing user speech or input
    THINKING = auto()      # AI brain is reasoning about the request
    PROCESSING = auto()    # A tool call is being prepared / validated
    EXECUTING = auto()     # A tool/action is actively running
    SPEAKING = auto()      # EV is producing a spoken/text response
    ERROR = auto()         # Something failed; showing an error to the user

    @property
    def label(self) -> str:
        """Human-readable label used in the UI."""
        return {
            AIState.IDLE: "IDLE",
            AIState.LISTENING: "LISTENING",
            AIState.THINKING: "THINKING",
            AIState.PROCESSING: "PROCESSING",
            AIState.EXECUTING: "EXECUTING",
            AIState.SPEAKING: "SPEAKING",
            AIState.ERROR: "ERROR",
        }[self]

    @property
    def accent_hex(self) -> str:
        """Accent color associated with this state, used by the UI core animation."""
        return {
            AIState.IDLE: "#3AA0C8",       # calm cyan
            AIState.LISTENING: "#33D6C0",  # bright teal
            AIState.THINKING: "#8A6CF0",   # violet
            AIState.PROCESSING: "#F0B93A", # amber
            AIState.EXECUTING: "#F0913A",  # orange
            AIState.SPEAKING: "#3AC8F0",   # sky blue
            AIState.ERROR: "#F0473A",      # red
        }[self]
