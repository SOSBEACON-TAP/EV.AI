"""
tools/system.py
-----------------
Read-only system information tools. These are all SAFE — no confirmation
required, since nothing here changes or deletes anything on the user's
PC.

Jarvis Pro adds a richer status report (battery, network, uptime, top
processes) so the assistant can give a concise "systems check".
"""

import os
import platform
import datetime
import socket

import psutil


def get_system_info() -> dict:
    """Current OS, CPU usage percent, RAM usage percent, and main drive
    storage usage percent."""
    try:
        disk_percent = psutil.disk_usage(os.path.abspath(os.sep)).percent
    except OSError:
        disk_percent = None

    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": disk_percent,
        "logical_cpu_count": psutil.cpu_count(logical=True),
    }


def get_datetime() -> dict:
    """Current date, time, and day of the week."""
    now = datetime.datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
    }


def get_system_status() -> dict:
    """
    Jarvis-style systems check: CPU, RAM, disk, battery, network,
    uptime, and the top CPU-consuming processes. Use for
    'status report', 'how is the system', 'systems check', etc.
    """
    info = get_system_info()
    now = datetime.datetime.now()

    battery = None
    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            battery = {
                "percent": round(bat.percent, 1),
                "plugged_in": bat.power_plugged,
                "secs_left": bat.secsleft if bat.secsleft and bat.secsleft > 0 else None,
            }
    except Exception:
        pass

    network = {"hostname": platform.node()}
    try:
        network["local_ip"] = socket.gethostbyname(socket.gethostname())
    except Exception:
        network["local_ip"] = None
    try:
        socket.getaddrinfo("one.one.one.one", 53, proto=socket.IPPROTO_UDP)
        network["internet"] = "reachable"
    except Exception:
        network["internet"] = "unreachable or restricted"

    try:
        boot = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime_s = int((now - boot).total_seconds())
        hours, rem = divmod(uptime_s, 3600)
        mins = rem // 60
        uptime = {"boot_time": boot.strftime("%Y-%m-%d %H:%M"), "uptime": f"{hours}h {mins}m"}
    except Exception:
        uptime = {}

    top = []
    try:
        psutil.cpu_percent(interval=0.2)
        by_name = {}
        for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
            try:
                info_p = p.info
                name = info_p.get("name") or "?"
                cpu = info_p.get("cpu_percent") or 0.0
                mem = info_p.get("memory_percent") or 0.0
                prev = by_name.get(name)
                if prev is None or cpu > prev["cpu_percent"]:
                    by_name[name] = {
                        "name": name,
                        "cpu_percent": round(cpu, 1),
                        "memory_percent": round(mem, 1),
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        top = sorted(by_name.values(), key=lambda x: x["cpu_percent"], reverse=True)[:8]
    except Exception:
        top = []

    return {
        **info,
        "battery": battery,
        "network": network,
        "uptime": uptime,
        "top_processes": top,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Jarvis system-monitoring tools
# ---------------------------------------------------------------------------
def get_top_processes(limit: int = 8) -> dict:
    """The apps using the most CPU and memory right now."""
    limit = max(1, min(int(limit or 8), 20))
    try:
        psutil.cpu_percent(interval=0.3)
        by_name: dict = {}
        for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
            try:
                i = p.info
                n = i.get("name") or "?"
                e = by_name.setdefault(n, {"name": n, "cpu_percent": 0.0, "memory_percent": 0.0, "count": 0})
                e["cpu_percent"] += i.get("cpu_percent") or 0.0
                e["memory_percent"] += i.get("memory_percent") or 0.0
                e["count"] += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        rows = list(by_name.values())
        for r in rows:
            r["cpu_percent"] = round(r["cpu_percent"], 1)
            r["memory_percent"] = round(r["memory_percent"], 1)
        return {
            "by_cpu": sorted(rows, key=lambda x: x["cpu_percent"], reverse=True)[:limit],
            "by_memory": sorted(rows, key=lambda x: x["memory_percent"], reverse=True)[:limit],
        }
    except Exception as e:
        return {"error": str(e)}


def get_disk_usage() -> dict:
    """Used / free space on every drive."""
    drives = []
    try:
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in (part.opts or "") or not part.fstype:
                continue
            try:
                u = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            drives.append({
                "drive": part.mountpoint,
                "total_gb": round(u.total / 1e9, 1),
                "used_gb": round(u.used / 1e9, 1),
                "free_gb": round(u.free / 1e9, 1),
                "percent_used": u.percent,
            })
    except Exception as e:
        return {"error": str(e)}
    return {"drives": drives}


def get_battery_status() -> dict:
    """Charge level, whether it is plugged in and the time left."""
    try:
        bat = psutil.sensors_battery()
    except Exception as e:
        return {"error": str(e)}
    if bat is None:
        return {"battery": "none", "message": "No battery found (desktop PC)."}
    mins = None
    if bat.secsleft and bat.secsleft > 0 and not bat.power_plugged:
        mins = int(bat.secsleft // 60)
    return {"percent": round(bat.percent, 1), "plugged_in": bool(bat.power_plugged), "minutes_left": mins}


def check_network() -> dict:
    """Is the network up, and is the internet reachable?"""
    out: dict = {"hostname": platform.node()}
    try:
        stats = psutil.net_if_stats()
        out["interfaces_up"] = sorted(n for n, s in stats.items() if s.isup and not n.lower().startswith(("lo", "loopback")))
    except Exception:
        out["interfaces_up"] = []
    try:
        s = socket.create_connection(("1.1.1.1", 53), timeout=3)
        s.close()
        out["internet"] = "reachable"
    except OSError:
        out["internet"] = "unreachable"
    try:
        io = psutil.net_io_counters()
        out["sent_mb"] = round(io.bytes_sent / 1e6, 1)
        out["received_mb"] = round(io.bytes_recv / 1e6, 1)
    except Exception:
        pass
    return out


def check_system_health() -> dict:
    """One-call health check: lists anything that needs attention."""
    from core.sysmon import evaluate
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    disks = get_disk_usage().get("drives", [])
    worst_disk = max((d["percent_used"] for d in disks), default=0)
    bat = get_battery_status()
    problems = evaluate(cpu, ram, worst_disk, bat.get("percent"), bat.get("plugged_in", True))
    return {
        "cpu_percent": cpu, "ram_percent": ram, "worst_disk_percent": worst_disk,
        "battery": bat, "problems": problems,
        "verdict": "All systems normal." if not problems else "Attention needed.",
    }
