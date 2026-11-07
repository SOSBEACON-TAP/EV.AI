"""
core/places.py
--------------
Location radar data for the PC.
  * approximate_location(): where this computer's internet connection appears to be (city level, from the IP address).
    A PC has no GPS, so this is only accurate to about the city. The phone's radar uses real GPS.
  * nearby_places(): real places around a point from OpenStreetMap (Overpass API).
Both make one internet request and only when you press the button.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

UA = {"User-Agent": "EV-AI-Desktop/1.0 (educational radar)"}


def distance_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(deg: float) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(((deg + 22.5) % 360) / 45)]


def nice(m: float) -> str:
    return f"{int(m)} m" if m < 1000 else f"{m / 1000:.1f} km"


_PS_LOCATION = (
    "Add-Type -AssemblyName System.Device; $w = New-Object System.Device.Location.GeoCoordinateWatcher('High'); "
    "$null = $w.TryStart($false, [TimeSpan]::FromSeconds(8)); $c = $w.Position.Location; "
    "if ($c -and -not $c.IsUnknown) { '{0},{1},{2}' -f $c.Latitude, $c.Longitude, $c.HorizontalAccuracy }"
)


def parse_ps_location(out: str) -> tuple[float, float, float] | None:
    """'28.61,77.2,35' -> (lat, lon, accuracy_m). Culture-safe (accepts decimal commas never; PowerShell -f uses invariant here)."""
    parts = [p.strip() for p in (out or "").strip().split(",")]
    if len(parts) != 3:
        return None
    try:
        lat, lon, acc = float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return lat, lon, acc


def windows_location(timeout: float = 15) -> dict | None:
    """The position Windows itself knows (Wi-Fi / GPS, needs Settings > Privacy > Location on), or None."""
    import subprocess, sys
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", _PS_LOCATION], capture_output=True, text=True,
                             timeout=timeout, creationflags=0x08000000).stdout
    except Exception:
        return None
    got = parse_ps_location(out)
    if not got:
        return None
    lat, lon, acc = got
    return {"lat": lat, "lon": lon, "city": "your position", "region": "", "country": "", "accuracy": acc, "source": "windows"}


def geocode(text: str, timeout: float = 10) -> dict | None:
    """Turn a place name the user typed ('Anna Nagar, Chennai') into a position (OpenStreetMap Nominatim)."""
    try:
        url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + urllib.parse.quote(text)
        d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode())
        if not d:
            return None
        name = d[0].get("display_name", text).split(",")
        return {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"]), "city": ", ".join(n.strip() for n in name[:2]),
                "region": "", "country": "", "source": "typed"}
    except Exception:
        return None


def approximate_location(timeout: float = 8) -> dict | None:
    """{lat, lon, city, region, country} from the IP address, or None."""
    try:
        req = urllib.request.Request("https://ipapi.co/json/", headers=UA)
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
        if "latitude" not in d:
            return None
        return {"lat": float(d["latitude"]), "lon": float(d["longitude"]), "city": d.get("city", ""),
                "region": d.get("region", ""), "country": d.get("country_name", "")}
    except Exception:
        return None


def build_query(lat: float, lon: float, radius: int) -> str:
    return ("[out:json][timeout:15];("
            f'node(around:{radius},{lat},{lon})[amenity~"^(hospital|clinic|pharmacy|police|fire_station|atm|bank|restaurant|cafe|fast_food|fuel|school|toilets|drinking_water|bus_station)$"];'
            f'node(around:{radius},{lat},{lon})[shop~"^(supermarket|convenience)$"];'
            ");out 80;")


def parse_places(text: str, lat: float, lon: float) -> list[dict]:
    out = []
    for e in json.loads(text).get("elements", []):
        tags = e.get("tags") or {}
        if "lat" not in e or "lon" not in e:
            continue
        kind = tags.get("amenity") or tags.get("shop") or "place"
        name = tags.get("name") or kind.replace("_", " ").capitalize()
        out.append({"name": name, "kind": kind.replace("_", " "), "meters": distance_m(lat, lon, e["lat"], e["lon"]),
                    "bearing": bearing_deg(lat, lon, e["lat"], e["lon"])})
    return sorted(out, key=lambda p: p["meters"])


def nearby_places(lat: float, lon: float, radius: int = 1000, timeout: float = 25) -> list[dict]:
    data = ("data=" + urllib.parse.quote(build_query(lat, lon, radius))).encode()
    req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=data, headers=UA)
    return parse_places(urllib.request.urlopen(req, timeout=timeout).read().decode(), lat, lon)
