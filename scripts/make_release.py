"""
scripts/make_release.py
-------------------------
Builds a clean, shareable release zip of EV.AI — code only, none of your
private files — and a matching version.json for "Check for updates".

    python scripts/make_release.py
    python scripts/make_release.py --url https://github.com/YOU/ev-ai/releases/latest --notes "Added X"

Output (in the dist/ folder, created next to main.py):
    dist/EV_AI-<version>.zip   upload this as your GitHub Release / download
    dist/version.json          upload this to wherever UPDATE_CHECK_URL points
                               (it carries the zip's SHA-256 so apps can verify the download)

It uses a WHITELIST: only the folders and files listed below are packed, so
your .env (API keys, email password), data/ (settings, memory, face model,
WhatsApp/browser logins), database/, venv/ and shortcuts can never leak in.
As a second safety net it scans every packed file for things that look like
API keys and refuses to build if it finds one.

The version number comes from VERSION in app_version.py — bump it first.
"""

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Same whitelist the in-app updater accepts (core/updater.py) — one source of truth,
# so a release can never contain something the updater would refuse.
sys.path.insert(0, str(ROOT))
from core.updater import ALLOWED_DIRS, ALLOWED_FILES  # noqa: E402

INCLUDE_DIRS = sorted(ALLOWED_DIRS)
INCLUDE_FILES = sorted(ALLOWED_FILES)
SKIP_PARTS = {"__pycache__", ".git", "venv", ".venv", "node_modules"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".lnk", ".db", ".log"}

# Things that look like real secrets. (.env.example's blank placeholders don't match.)
SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "Google API key"),
    (re.compile(r"gsk_[0-9A-Za-z]{30,}"), "Groq API key"),
    (re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}"), "Anthropic API key"),
    (re.compile(r"sk-(?:proj-)?[0-9A-Za-z_\-]{30,}"), "OpenAI-style API key"),
    (re.compile(r"(?im)^\s*(?:AI_API_KEY|EMAIL_APP_PASSWORD)\s*=\s*['\"]?[^\s'\"#]{6,}"), "a filled-in secret line"),
]


def app_version() -> str:
    text = (ROOT / "app_version.py").read_text(encoding="utf-8")
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    if not m:
        sys.exit("Couldn't find VERSION in app_version.py.")
    return m.group(1)


def app_notes() -> str:
    text = (ROOT / "app_version.py").read_text(encoding="utf-8")
    m = re.search(r'RELEASE_NOTES\s*=\s*\(?\s*((?:"[^"]*"\s*)+)', text)
    return "".join(re.findall(r'"([^"]*)"', m.group(1))) if m else ""


def collect() -> list[Path]:
    files: list[Path] = []
    for name in INCLUDE_FILES:
        path = ROOT / name
        if path.is_file():
            files.append(path)
    for folder in INCLUDE_DIRS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if (path.is_file() and not (SKIP_PARTS & set(path.relative_to(ROOT).parts))
                    and path.suffix.lower() not in SKIP_SUFFIXES):
                files.append(path)
    return files


def scan_for_secrets(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        if path.suffix.lower() in {".png", ".ico", ".wav", ".jpg", ".jpeg", ".mp3"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"{path.relative_to(ROOT)}: looks like {label}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a clean EV.AI release zip.")
    parser.add_argument("--url", default="", help="Release page people can open (goes in version.json)")
    parser.add_argument("--zip-url", default="", help="Direct https link to the zip, so EV.AI can install it itself")
    parser.add_argument("--base-url", default="",
                        help="Folder the zip will be uploaded to; zip link = BASE/EV_AI-<version>.zip "
                             "(GitHub: https://github.com/YOU/REPO/releases/latest/download)")
    parser.add_argument("--notes", default="", help="One-line release notes (goes in version.json)")
    args = parser.parse_args()

    version = app_version()
    files = collect()
    if not any(p.name == "main.py" for p in files):
        sys.exit("main.py not found — run this from inside the EV_AI folder.")

    problems = scan_for_secrets(files)
    if problems:
        print("STOPPED — possible secrets found in files that would be published:")
        for line in problems:
            print("  -", line)
        print("Remove them and run again.")
        return 1

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / f"EV_AI-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path, Path("EV_AI") / path.relative_to(ROOT))

    zip_url = args.zip_url or (f"{args.base_url.rstrip('/')}/{zip_path.name}" if args.base_url else "")
    sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    version_json = dist / "version.json"
    version_json.write_text(
        json.dumps({"version": version, "url": args.url, "zip_url": zip_url,
                    "sha256": sha256, "notes": args.notes or app_notes()}, indent=2) + "\n",
        encoding="utf-8",
    )
    size_mb = zip_path.stat().st_size / 1_000_000
    print(f"Built {zip_path.name} ({len(files)} files, {size_mb:.1f} MB)")
    print(f"Wrote {version_json.name} for version {version}")
    if not zip_url:
        print("NOTE: no --zip-url/--base-url given, so friends' apps can tell them about this "
              "update but can't install it by themselves.")
    print("Not included (by design): .env, data/, database/, venv/, shortcuts, logs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
