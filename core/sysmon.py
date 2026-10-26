"""
core/sysmon.py
--------------
Thresholds and warning logic for Jarvis' system monitor. Pure logic (no
Qt, no psutil) so it can be tested anywhere.
"""

CPU_LIMIT = 90        # percent, must stay above for CPU_TICKS readings in a row
CPU_TICKS = 5
RAM_LIMIT = 90
DISK_LIMIT = 90
BATTERY_LIMIT = 15
COOLDOWN_S = 600      # don't repeat the same warning for 10 minutes


def evaluate(cpu, ram, disk, battery, plugged) -> list:
    """Current problems as plain sentences (no timing; used by 'health check')."""
    out = []
    if cpu is not None and cpu >= CPU_LIMIT:
        out.append(f"CPU is at {cpu:.0f}%")
    if ram is not None and ram >= RAM_LIMIT:
        out.append(f"memory is {ram:.0f}% full")
    if disk is not None and disk >= DISK_LIMIT:
        out.append(f"a drive is {disk:.0f}% full")
    if battery is not None and not plugged and battery <= BATTERY_LIMIT:
        out.append(f"battery is low at {battery:.0f}%")
    return out


class SystemWatch:
    """Feed it a reading every couple of seconds; it returns new warnings to speak."""

    def __init__(self):
        self._cpu_high = 0
        self._last: dict = {}

    def update(self, cpu, ram, disk, battery, plugged, now: float) -> list:
        self._cpu_high = self._cpu_high + 1 if (cpu is not None and cpu >= CPU_LIMIT) else 0
        wanted = {}
        if self._cpu_high >= CPU_TICKS:
            wanted["cpu"] = f"CPU has been above {CPU_LIMIT}% for a while ({cpu:.0f}%)."
        if ram is not None and ram >= RAM_LIMIT:
            wanted["ram"] = f"Memory is {ram:.0f}% full."
        if disk is not None and disk >= DISK_LIMIT:
            wanted["disk"] = f"A drive is {disk:.0f}% full."
        if battery is not None and not plugged and battery <= BATTERY_LIMIT:
            wanted["battery"] = f"Battery is low at {battery:.0f}%. Please plug in."
        out = []
        for key, msg in wanted.items():
            if now - self._last.get(key, -1e9) >= COOLDOWN_S:
                self._last[key] = now
                out.append(msg)
        return out
