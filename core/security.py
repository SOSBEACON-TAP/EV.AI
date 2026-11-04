"""
core/security.py
----------------
The engine behind ULTRON's HACK terminal: a DEFENSIVE security toolkit that checks YOUR OWN
computer, YOUR OWN network and files you give it. Nothing here attacks anything.

  * dark_scan()      : firewall, antivirus, updates, startup programs, open ports, privacy use
  * scan_network()   : devices on your own Wi-Fi/LAN (private address ranges only)
  * password tools   : strength test, strong generator, local reuse audit, optional leak check
  * analyze_website(): HTTPS, certificate, security headers, cookie flags (one normal request)
  * forensics        : hashes, metadata, disguised file types, "downloaded from internet" mark
  * simulate_*       : animated EDUCATIONAL demos using made-up data only; they touch nothing real

A finding is {"level": "ok" | "info" | "warn" | "bad", "text": str}.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import ipaddress
import math
import os
import random
import re
import secrets
import socket
import ssl
import string
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

IS_WIN = os.name == "nt"
_NOWIN = 0x08000000 if IS_WIN else 0


def F(level: str, text: str) -> dict:
    return {"level": level, "text": text}


# ------------------------------------------------------------------ helpers
def _run(cmd: list[str], timeout: float = 25) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NOWIN)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def _ps(script: str, timeout: float = 30) -> str:
    return _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


def score(findings: list[dict]) -> int:
    """Security health 0-100 from real findings: each bad costs 25, each warn costs 8."""
    value = 100 - 25 * sum(1 for f in findings if f["level"] == "bad") - 8 * sum(1 for f in findings if f["level"] == "warn")
    return max(0, min(100, value))


# ------------------------------------------------------------ system checks
def firewall_findings() -> list[dict]:
    if not IS_WIN:
        return [F("info", "Firewall check works on Windows.")]
    out = _run(["netsh", "advfirewall", "show", "allprofiles", "state"])
    if not out.strip():
        return [F("warn", "Couldn't read the Windows Firewall status.")]
    findings, profile = [], ""
    for line in out.splitlines():
        line = line.strip()
        if "Profile Settings" in line:
            profile = line.split(" Profile")[0]
        m = re.match(r"State\s+(\w+)", line)
        if m:
            on = m.group(1).upper() == "ON"
            findings.append(F("ok" if on else "bad", f"Firewall {profile or 'profile'}: {'ON' if on else 'OFF'}"))
    return findings or [F("warn", "Couldn't understand the firewall status.")]


def enable_firewall() -> tuple[bool, str]:
    """Turns the Windows Firewall ON for all profiles (needs administrator rights). There is no 'turn off'."""
    if not IS_WIN:
        return False, "Only on Windows."
    out = _run(["netsh", "advfirewall", "set", "allprofiles", "state", "on"])
    if "Ok." in out or "OK" in out:
        return True, "Windows Firewall is ON for all profiles."
    return False, "Couldn't change it. Run EV AI as administrator, or open Windows Security, Firewall."


def defender_findings() -> list[dict]:
    if not IS_WIN:
        return [F("info", "Antivirus check works on Windows.")]
    out = _ps("$s=Get-MpComputerStatus; \"$($s.AntivirusEnabled)|$($s.RealTimeProtectionEnabled)|$($s.AntivirusSignatureAge)\"")
    parts = out.strip().splitlines()[-1].split("|") if out.strip() else []
    if len(parts) != 3:
        return [F("warn", "Couldn't read Microsoft Defender (another antivirus may be installed).")]
    av, rt, age = parts[0] == "True", parts[1] == "True", int(parts[2]) if parts[2].strip().isdigit() else -1
    res = [F("ok" if av else "bad", f"Antivirus: {'enabled' if av else 'DISABLED'}"),
           F("ok" if rt else "bad", f"Real-time protection: {'on' if rt else 'OFF'}")]
    if age >= 0:
        res.append(F("ok" if age <= 3 else "warn", f"Virus definitions are {age} day(s) old"))
    return res


def update_findings() -> list[dict]:
    if not IS_WIN:
        return [F("info", "Update check works on Windows.")]
    out = _ps("(Get-HotFix | Where-Object {$_.InstalledOn} | Sort-Object InstalledOn -Descending | Select-Object -First 1).InstalledOn.ToString('yyyy-MM-dd')")
    try:
        days = (datetime.now() - datetime.strptime(out.strip().splitlines()[-1], "%Y-%m-%d")).days
    except Exception:
        return [F("info", "Couldn't read when Windows last installed a security update.")]
    level = "ok" if days <= 45 else "warn" if days <= 120 else "bad"
    return [F(level, f"Last Windows update installed {days} day(s) ago" + ("" if level == "ok" else ". Run Windows Update."))]


def startup_items() -> list[tuple[str, str]]:
    """[(name, command)] from the Run keys of the registry (current user and all users)."""
    items: list[tuple[str, str]] = []
    if not IS_WIN:
        return items
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                    for i in range(winreg.QueryInfoKey(key)[1]):
                        name, value, _ = winreg.EnumValue(key, i)
                        items.append((name, str(value)))
            except OSError:
                pass
    except ImportError:
        pass
    return items


def startup_findings() -> list[dict]:
    items = startup_items()
    if not IS_WIN:
        return [F("info", "Startup check works on Windows.")]
    res = [F("ok" if len(items) <= 10 else "warn", f"{len(items)} program(s) start with Windows")]
    for name, cmd in items:
        low = cmd.lower()
        if any(x in low for x in ("\\temp\\", "\\downloads\\", "appdata\\local\\temp")):
            res.append(F("warn", f"Startup item '{name}' runs from a temporary/download folder: {cmd[:80]}"))
    return res


_RISKY_PORTS = {21: "FTP", 23: "Telnet", 135: "RPC", 139: "NetBIOS", 445: "SMB file sharing", 3389: "Remote Desktop", 5900: "VNC"}


def port_findings() -> list[dict]:
    try:
        import psutil
        conns = psutil.net_connections(kind="inet")
    except Exception:
        return [F("info", "Couldn't list open ports (try running as administrator).")]
    exposed: dict[int, str] = {}
    for c in conns:
        if c.status == "LISTEN" and c.laddr and c.laddr.ip not in ("127.0.0.1", "::1"):
            try:
                name = psutil.Process(c.pid).name() if c.pid else "?"
            except Exception:
                name = "?"
            exposed[c.laddr.port] = name
    res = [F("info", f"{len(exposed)} port(s) listen for connections from other devices")]
    for port, name in sorted(exposed.items()):
        if port in _RISKY_PORTS:
            res.append(F("warn", f"Port {port} ({_RISKY_PORTS[port]}) is open, used by {name}. Close it if you don't need it."))
    return res


def privacy_findings() -> list[dict]:
    """GHOST MODE: which apps recently used the camera, microphone or location (Windows privacy log)."""
    if not IS_WIN:
        return [F("info", "Privacy audit works on Windows.")]
    res = []
    try:
        import winreg
        base = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
        for cap, label in (("webcam", "Camera"), ("microphone", "Microphone"), ("location", "Location")):
            apps = []
            for sub in ("NonPackaged", ""):
                path = f"{base}\\{cap}" + (f"\\{sub}" if sub else "")
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            name = winreg.EnumKey(key, i)
                            try:
                                with winreg.OpenKey(key, name) as app:
                                    start = winreg.QueryValueEx(app, "LastUsedTimeStart")[0]
                                    stop = winreg.QueryValueEx(app, "LastUsedTimeStop")[0]
                                    if start and not stop:
                                        apps.append(name.replace("#", "\\").split("\\")[-1] + " (IN USE NOW)")
                                    elif start:
                                        apps.append(name.replace("#", "\\").split("\\")[-1])
                            except OSError:
                                pass
                except OSError:
                    pass
            if apps:
                res.append(F("warn" if any("IN USE" in a for a in apps) else "info",
                             f"{label} used by: " + ", ".join(sorted(set(apps))[:8])))
            else:
                res.append(F("ok", f"{label}: no app has used it recently"))
    except ImportError:
        pass
    return res or [F("info", "No privacy information available.")]


def dark_scan(progress=None) -> list[dict]:
    """Full local assessment. progress(text) is called before each stage."""
    findings: list[dict] = []
    for label, fn in (("Firewall", firewall_findings), ("Antivirus", defender_findings),
                      ("Windows updates", update_findings), ("Startup programs", startup_findings),
                      ("Open ports", port_findings), ("Privacy (camera, mic, location)", privacy_findings)):
        if progress:
            progress(label)
        findings.extend(fn())
    return findings


# -------------------------------------------------------------- network scan
def local_network() -> tuple[str, ipaddress.IPv4Network] | None:
    """(my IP, my /24 network) on a private range, or None."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))     # no packet is sent; just picks the right interface
        ip = s.getsockname()[0]
        s.close()
        addr = ipaddress.ip_address(ip)
        if not addr.is_private:
            return None
        return ip, ipaddress.ip_network(f"{ip}/24", strict=False)
    except Exception:
        return None


def _ping(ip: str) -> bool:
    cmd = ["ping", "-n", "1", "-w", "400", ip] if IS_WIN else ["ping", "-c", "1", "-W", "1", ip]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=3, creationflags=_NOWIN).returncode == 0
    except Exception:
        return False


def parse_arp(text: str) -> dict[str, str]:
    """{ip: mac} from `arp -a` output (Windows and Linux styles)."""
    found = {}
    for m in re.finditer(r"(\d{1,3}(?:\.\d{1,3}){3})\)?\s+(?:at\s+)?([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})", text):
        found[m.group(1)] = m.group(2).lower().replace("-", ":")
    return found


def _host(ip: str) -> str:
    try:
        socket.setdefaulttimeout(1.0)
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""
    finally:
        socket.setdefaulttimeout(None)


def scan_network(progress=None) -> tuple[str, list[dict]]:
    """Finds devices on YOUR OWN private network. Refuses public address ranges."""
    net = local_network()
    if not net:
        return "", []
    my_ip, network = net
    hosts = [str(h) for h in network.hosts()]
    if progress:
        progress(f"Sweeping {network} ({len(hosts)} addresses)")
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        alive = {ip for ip, ok in zip(hosts, pool.map(_ping, hosts)) if ok}
    arp = parse_arp(_run(["arp", "-a"]))
    ips = sorted(alive | {ip for ip in arp if ip in set(hosts)}, key=lambda x: tuple(int(p) for p in x.split(".")))
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        names = dict(zip(ips, pool.map(_host, ips)))
    devices = []
    for ip in ips:
        name = names.get(ip, "")
        devices.append({"ip": ip, "mac": arp.get(ip, "?"), "name": name or "(no name)", "online": ip in alive,
                        "me": ip == my_ip, "unknown": not name and ip != my_ip})
    return my_ip, devices


# ------------------------------------------------------- what is around me
def parse_wifi(text: str) -> list[dict]:
    """Parses `netsh wlan show networks mode=bssid` into [{ssid, signal, auth, channel}]."""
    nets, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"SSID \d+ : (.*)", line)
        if m:
            cur = {"ssid": m.group(1).strip() or "(hidden)", "signal": 0, "auth": "?", "channel": 0}
            nets.append(cur)
        elif cur is not None:
            k, _, v = line.partition(":")
            k, v = k.strip().lower(), v.strip()
            if k == "authentication":
                cur["auth"] = v
            elif k == "signal" and v.endswith("%") and v[:-1].isdigit():
                cur["signal"] = max(cur["signal"], int(v[:-1]))
            elif k == "channel" and v.isdigit() and not cur["channel"]:
                cur["channel"] = int(v)
    return nets


def wifi_security_level(auth: str) -> str:
    a = auth.lower()
    if "open" in a:
        return "bad"
    if "wep" in a or ("wpa" in a and "wpa2" not in a and "wpa3" not in a):
        return "warn"
    return "ok"


def nearby_wifi() -> list[dict]:
    """Wi-Fi networks your own adapter can hear (passive listing, like the Windows Wi-Fi menu)."""
    if not IS_WIN:
        return []
    return parse_wifi(_run(["netsh", "wlan", "show", "networks", "mode=bssid"]))


def wifi_findings(nets: list[dict]) -> list[dict]:
    if not nets:
        return [F("info", "No Wi-Fi networks heard (no adapter, or Wi-Fi is off).")]
    res = [F("info", f"{len(nets)} Wi-Fi network(s) around you")]
    for n in sorted(nets, key=lambda x: -x["signal"]):
        lv = wifi_security_level(n["auth"])
        note = {"ok": "", "warn": "  (old, weak security)", "bad": "  (OPEN: anyone can listen)"}[lv]
        res.append(F(lv, f"{n['ssid']:<24} signal {n['signal']:>3}%  ch {n['channel'] or '?':<3} {n['auth']}{note}"))
    return res


# ------------------------------------------------------------ password lab
_COMMON = {"password", "123456", "123456789", "qwerty", "111111", "12345678", "abc123", "password1", "iloveyou",
           "admin", "welcome", "letmein", "monkey", "dragon", "football", "login", "princess", "sunshine",
           "123123", "000000", "qwerty123", "1q2w3e4r", "zaq12wsx", "passw0rd", "p@ssw0rd", "ev", "evai"}
_WALKS = ("qwerty", "asdfgh", "zxcvbn", "qazwsx", "1qaz2wsx", "123456", "654321", "abcdef", "abcd")


def password_report(pw: str) -> dict:
    """Strength test. Runs only on this PC; the password is never stored or sent anywhere."""
    issues = []
    pool = (26 if re.search(r"[a-z]", pw) else 0) + (26 if re.search(r"[A-Z]", pw) else 0) + \
           (10 if re.search(r"\d", pw) else 0) + (33 if re.search(r"[^A-Za-z0-9]", pw) else 0)
    entropy = len(pw) * math.log2(pool) if pool and pw else 0.0
    low = pw.lower()
    if low in _COMMON or re.sub(r"[^a-z0-9]", "", low) in _COMMON:
        issues.append("It is one of the most common passwords in the world.")
        entropy = min(entropy, 10)
    if len(pw) < 12:
        issues.append("Shorter than 12 characters. Length matters most.")
    if any(w in low for w in _WALKS):
        issues.append("Contains a keyboard or alphabet pattern (qwerty, 123456, abcd).")
        entropy *= 0.6
    if re.search(r"(.)\1{2,}", pw):
        issues.append("Repeats the same character three or more times.")
        entropy *= 0.8
    if re.search(r"(19|20)\d\d", pw):
        issues.append("Contains a year, which attackers try first.")
        entropy *= 0.85
    if re.fullmatch(r"[A-Za-z]+\d{1,4}[^A-Za-z0-9]?", pw):
        issues.append("Pattern 'Word + digits': very predictable.")
        entropy *= 0.7
    if pool <= 36 and pw:
        issues.append("Uses only one or two kinds of characters.")
    seconds = (2 ** entropy) / 2 / 1e10        # offline attack at 10 billion guesses per second
    rating = "VERY WEAK" if entropy < 28 else "WEAK" if entropy < 40 else "FAIR" if entropy < 60 else "STRONG" if entropy < 80 else "EXCELLENT"
    return {"entropy": round(entropy, 1), "rating": rating, "crack_time": human_time(seconds), "issues": issues}


def human_time(seconds: float) -> str:
    if seconds < 1:
        return "instantly"
    for limit, unit in ((60, "second"), (3600, "minute"), (86400, "hour"), (86400 * 365, "day"),
                        (86400 * 365 * 1000, "year"), (86400 * 365 * 1e6, "thousand years")):
        if seconds < limit:
            div = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "year": 86400 * 365,
                   "thousand years": 86400 * 365 * 1000}[unit]
            n = seconds / div
            return f"about {n:.0f} {unit}{'s' if round(n) != 1 else ''}"
    return "millions of years"


def generate_password(length: int = 18, symbols: bool = True) -> str:
    length = max(8, min(64, length))
    alphabet = string.ascii_letters + string.digits + ("!@#$%^&*-_=+?" if symbols else "")
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw) and re.search(r"\d", pw) and \
                (not symbols or re.search(r"[^A-Za-z0-9]", pw)):
            return pw


def audit_passwords(passwords: list[str]) -> list[dict]:
    """Local reuse audit: pass the passwords you use (one per account). Finds duplicates and weak ones."""
    findings, seen = [], {}
    for i, pw in enumerate(p for p in passwords if p):
        seen.setdefault(pw, []).append(i + 1)
    reused = [idx for idx in seen.values() if len(idx) > 1]
    for idx in reused:
        findings.append(F("bad", f"Accounts {', '.join(map(str, idx))} use the SAME password. Make each one different."))
    for pw, idx in seen.items():
        rep = password_report(pw)
        if rep["rating"] in ("VERY WEAK", "WEAK"):
            findings.append(F("warn", f"Account {idx[0]}: {rep['rating']} password ({rep['crack_time']} to crack)"))
    if not findings:
        findings.append(F("ok", "No reused or weak passwords in this list."))
    return findings


def leak_check(pw: str, timeout: float = 8) -> tuple[bool, str]:
    """Have I Been Pwned range API. Only the first 5 characters of the SHA-1 hash are sent (k-anonymity)."""
    sha = hashlib.sha1(pw.encode("utf-8")).hexdigest().upper()
    try:
        req = urllib.request.Request(f"https://api.pwnedpasswords.com/range/{sha[:5]}", headers={"User-Agent": "EV.AI"})
        body = urllib.request.urlopen(req, timeout=timeout).read().decode()
    except Exception as e:
        return False, f"Couldn't reach the leak database: {e}"
    for line in body.splitlines():
        suffix, _, count = line.partition(":")
        if suffix.strip() == sha[5:]:
            return True, f"FOUND in {int(count):,} known data leaks. Never use it again."
    return True, "Not found in known leaks."


# --------------------------------------------------------- website analyzer
_HEADERS = {
    "strict-transport-security": ("HSTS (forces HTTPS)", "bad"),
    "content-security-policy": ("Content-Security-Policy (blocks injected scripts)", "warn"),
    "x-frame-options": ("X-Frame-Options (blocks clickjacking)", "warn"),
    "x-content-type-options": ("X-Content-Type-Options (stops type sniffing)", "warn"),
    "referrer-policy": ("Referrer-Policy (limits data leaked to other sites)", "info"),
    "permissions-policy": ("Permissions-Policy (limits camera/mic use)", "info"),
}


def analyze_website(url: str, timeout: float = 10) -> list[dict]:
    """One normal page request + one TLS handshake. Use it on sites you own or have permission to review."""
    url = (url or "").strip()
    if not url:
        return [F("warn", "Type a website address first.")]
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    host = re.sub(r"^https?://", "", url, flags=re.I).split("/")[0].split(":")[0]
    findings = [F("info", f"Analyzing {host} (one normal page request, nothing intrusive)")]
    # certificate
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as raw, ctx.wrap_socket(raw, server_hostname=host) as tls:
            cert = tls.getpeercert()
            expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
            days = (expires - datetime.utcnow()).days
            findings.append(F("ok", f"HTTPS works, certificate valid ({tls.version()})"))
            findings.append(F("ok" if days > 30 else "warn" if days >= 0 else "bad",
                              f"Certificate expires in {days} day(s)" if days >= 0 else "Certificate has EXPIRED"))
    except ssl.SSLCertVerificationError as e:
        findings.append(F("bad", f"HTTPS certificate problem: {e.verify_message}"))
    except Exception as e:
        findings.append(F("bad", f"HTTPS is not available on port 443 ({type(e).__name__})"))
    # headers + cookies
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EV.AI-SecurityCheck"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            cookies = resp.headers.get_all("Set-Cookie") or []
            final = resp.geturl()
        if final.startswith("http://"):
            findings.append(F("bad", "The site ends on plain HTTP (not encrypted)."))
        for key, (label, level) in _HEADERS.items():
            findings.append(F("ok", f"{label}: present") if key in headers else F(level, f"Missing {label}"))
        if "server" in headers and re.search(r"\d", headers["server"]):
            findings.append(F("warn", f"Server reveals its version: {headers['server']}"))
        if "x-powered-by" in headers:
            findings.append(F("warn", f"X-Powered-By reveals technology: {headers['x-powered-by']}"))
        for c in cookies[:5]:
            name = c.split("=")[0]
            miss = [f for f, ok in (("Secure", "secure" in c.lower()), ("HttpOnly", "httponly" in c.lower()),
                                    ("SameSite", "samesite" in c.lower())) if not ok]
            findings.append(F("warn", f"Cookie '{name}' missing: {', '.join(miss)}") if miss else F("ok", f"Cookie '{name}' has Secure, HttpOnly, SameSite"))
    except urllib.error.HTTPError as e:
        findings.append(F("info", f"The site answered with HTTP {e.code}; headers not checked."))
    except Exception as e:
        findings.append(F("warn", f"Couldn't load the page: {type(e).__name__}"))
    return findings


# --------------------------------------------------------------- forensics
_RISKY_EXT = {".exe", ".scr", ".bat", ".cmd", ".com", ".pif", ".vbs", ".js", ".jse", ".wsf", ".ps1", ".hta",
              ".jar", ".lnk", ".msi", ".dll", ".reg"}
_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".txt", ".mp3", ".mp4", ".zip"}
_MAGIC = {b"MZ": "Windows program (EXE/DLL)", b"%PDF": "PDF document", b"PK\x03\x04": "ZIP / Office file",
          b"\xff\xd8\xff": "JPEG image", b"\x89PNG": "PNG image"}


def file_report(path: str) -> list[dict]:
    p = Path(path.strip().strip('"'))
    if not p.is_file():
        return [F("warn", "That file wasn't found.")]
    st = p.stat()
    res = [F("info", f"File: {p.name}"), F("info", f"Size: {st.st_size:,} bytes"),
           F("info", f"Created: {datetime.fromtimestamp(st.st_ctime):%Y-%m-%d %H:%M}   Modified: {datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M}")]
    md5, sha1, sha256 = hashlib.md5(), hashlib.sha1(), hashlib.sha256()
    head = b""
    with open(p, "rb") as fh:
        head = fh.read(8)
        fh.seek(0)
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            md5.update(chunk), sha1.update(chunk), sha256.update(chunk)
    res += [F("info", f"MD5:    {md5.hexdigest()}"), F("info", f"SHA-1:  {sha1.hexdigest()}"),
            F("info", f"SHA-256: {sha256.hexdigest()}  (paste it into virustotal.com to check it)")]
    ext = p.suffix.lower()
    kind = next((v for k, v in _MAGIC.items() if head.startswith(k)), "")
    if kind:
        res.append(F("info", f"Real file type: {kind}"))
        if kind.startswith("Windows program") and ext not in {".exe", ".dll", ".scr", ".sys"}:
            res.append(F("bad", f"DISGUISED: it is a program but named '{ext or 'no extension'}'."))
        if ext in _DOC_EXT and kind.startswith("Windows program"):
            res.append(F("bad", "A document name hiding a program. Do not open it."))
    parts = p.name.lower().split(".")
    if len(parts) > 2 and "." + parts[-1] in _RISKY_EXT and "." + parts[-2] in _DOC_EXT:
        res.append(F("bad", f"Double extension '.{parts[-2]}.{parts[-1]}' is a classic trick to hide a program."))
    elif ext in _RISKY_EXT:
        res.append(F("warn", f"'{ext}' files can run code. Open only if you trust the source."))
    try:
        zone = Path(str(p) + ":Zone.Identifier").read_text(errors="ignore")
        m = re.search(r"HostUrl=(.+)", zone)
        res.append(F("warn", "Downloaded from the internet" + (f": {m.group(1).strip()[:90]}" if m else "")))
    except OSError:
        pass
    return res


def scan_folder(folder: str, limit: int = 400) -> list[dict]:
    """Checks a folder (default: Downloads) for risky or disguised files."""
    base = Path(folder).expanduser()
    if not base.is_dir():
        return [F("warn", "That folder wasn't found.")]
    res, n = [], 0
    for p in base.rglob("*"):
        if n >= limit:
            res.append(F("info", f"Stopped after {limit} files."))
            break
        if not p.is_file():
            continue
        n += 1
        parts = p.name.lower().split(".")
        if len(parts) > 2 and "." + parts[-1] in _RISKY_EXT and "." + parts[-2] in _DOC_EXT:
            res.append(F("bad", f"Disguised: {p.name}"))
        elif p.suffix.lower() in _RISKY_EXT:
            res.append(F("info", f"Program/script: {p.name}"))
    res.insert(0, F("info", f"Looked at {n} file(s) in {base}"))
    if len(res) == 1:
        res.append(F("ok", "Nothing suspicious found."))
    return res


# ---------------------------------------------------- educational simulations
def simulate_portscan() -> list[str]:
    host = "203.0.113.7"          # documentation-only address: it does not exist
    ports = [(21, "ftp", "closed"), (22, "ssh", "open"), (23, "telnet", "closed"), (80, "http", "open"),
             (443, "https", "open"), (445, "smb", "filtered"), (3389, "rdp", "closed"), (8080, "http-proxy", "open")]
    lines = [f"[SIMULATION] Nothing real is scanned. Fictional target {host}", f"[SIM] Scanning {host} ..."]
    lines += [f"[SIM] port {p:<5} {name:<11} {state}" for p, name, state in ports]
    lines += ["[SIM] LESSON: every 'open' port is a door. Close what you don't use, and keep a firewall on."]
    return lines


def simulate_bruteforce() -> list[str]:
    guesses = ["123456", "password", "qwerty", "letmein", "admin123", "welcome1", "iloveyou", "Tr0ub4dor&3"]
    lines = ["[SIMULATION] Fictional account 'demo_user'. Dummy passwords only.", "[SIM] Starting dictionary attack ..."]
    for i, g in enumerate(guesses, 1):
        lines.append(f"[SIM] attempt {i:>2}: {g:<12} " + ("-> ACCESS GRANTED (it was guessed!)" if g == "welcome1" else "-> denied"))
        if g == "welcome1":
            break
    lines += ["[SIM] After 3 wrong tries a real site locks the account or adds a delay. That stops this attack.",
              "[SIM] LESSON: unique, long passwords + two-step login beat guessing."]
    return lines


def simulate_firewall() -> list[str]:
    rnd = random.Random(11)
    lines = ["[SIMULATION] Fictional packets against a fictional firewall.", "[FW] Rules loaded: block inbound except 443"]
    for i in range(8):
        ip = f"198.51.100.{rnd.randint(2, 250)}"
        port = rnd.choice([22, 23, 445, 3389, 8080, 443])
        lines.append(f"[FW] {ip:<15} -> :{port:<5} " + ("ALLOWED (web)" if port == 443 else "BLOCKED"))
    lines.append("[FW] LESSON: a firewall drops everything you didn't ask for.")
    return lines


def simulate_phishing() -> list[str]:
    return ["[SIMULATION] A made-up phishing email. Learn the red flags:", "",
            "  From:    security@paypa1-support.example   <- [FLAG 1] misspelled domain (paypa1)",
            "  Subject: URGENT!!! Your account will be closed in 24 hours   <- [FLAG 2] fear and urgency",
            "  Body:    Dear customer, click here to verify your password: http://paypal.verify-now.example/login",
            "                                                              <- [FLAG 3] link goes somewhere else",
            "  Attach:  invoice.pdf.exe                                    <- [FLAG 4] double extension = program", "",
            "[SIM] LESSON: check the sender's real address, hover before you click, never log in from an email link."]


def simulate_crack_demo() -> list[str]:
    samples = ["123456", "password1", "Summer2024", "Tr0ub4dor&3", "correct horse battery staple", "k9#Vq2!xLm8@Zp4w"]
    lines = ["[SIMULATION] Fictional sample passwords. Nothing is cracked; the time is calculated:"]
    for s in samples:
        r = password_report(s)
        lines.append(f"[SIM] {s:<30} {r['rating']:<10} would take {r['crack_time']}")
    lines.append("[SIM] LESSON: length and randomness add years. Use a password manager.")
    return lines


def simulate_attack_map() -> list[str]:
    rnd = random.Random(3)
    kinds = ["port scan", "brute-force login", "malware download", "phishing link", "DDoS flood"]
    lines = ["[SIMULATION] Fictional attack feed (made-up addresses):"]
    for _ in range(8):
        lines.append(f"[SIM] 192.0.2.{rnd.randint(2, 250):<3} -> your-pc   {rnd.choice(kinds):<18} "
                     f"{'BLOCKED' if rnd.random() < 0.8 else 'DETECTED'}")
    lines.append("[SIM] LESSON: attacks are constant and automatic; layers of defence stop most of them.")
    return lines


SIMULATIONS = {
    "port scan": simulate_portscan, "brute force": simulate_bruteforce, "firewall": simulate_firewall,
    "phishing": simulate_phishing, "password cracking": simulate_crack_demo, "attack map": simulate_attack_map,
}
