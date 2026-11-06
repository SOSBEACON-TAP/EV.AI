"""
core/browser_bridge.py
----------------------
Lets the EV AI Chrome extension talk to EV AI on THIS PC. Nothing leaves the computer here.

  * Listens only on 127.0.0.1 (never reachable from other devices).
  * The extension must pair once with a 6-digit code shown in EV AI Settings. After that it
    sends a secret token with every request. Wrong codes lock pairing for a minute.
  * Requests from web pages are refused (only chrome-extension:// origins, and only our host name).
  * EV can only send a short allow-list of browser commands (open, search, scroll, click, tabs).
  * A page is only read when YOU ask (the popup button or a voice command), never in the background.

Extension -> EV:  POST /pair  POST /ask  GET /poll (long-poll for commands)  POST /page
EV -> extension:  commands such as {"action": "scroll", "dir": "down"}
"""

from __future__ import annotations

import hmac
import json
import queue
import re
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote_plus

PORT = 47615
HOST = "127.0.0.1"
MAX_BODY = 600_000            # ~600 KB of page text at most
CONNECTED_WITHIN_S = 45       # extension counts as connected if it polled this recently

ACTIONS = {"open_url", "search", "scroll", "click", "new_tab", "close_tab", "next_tab", "prev_tab",
           "back", "forward", "reload", "switch_tab", "page_text"}


def _store() -> Path:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "data" / "browser_bridge.json"


def clean_command(cmd: dict) -> dict | None:
    """Validates a command from EV before it is sent to the browser. Returns the safe version or None."""
    if not isinstance(cmd, dict) or cmd.get("action") not in ACTIONS:
        return None
    a = cmd["action"]
    out = {"action": a}
    if a == "open_url":
        url = str(cmd.get("url", "")).strip()
        if not url:
            return None
        scheme = re.match(r"^([a-z][a-z0-9+.-]*):(?!\d)", url, re.I)      # 'example.com:8080' is a port, not a scheme
        if scheme and scheme.group(1).lower() not in ("http", "https"):   # no javascript:, file:, chrome: ...
            return None
        if not scheme:
            url = "https://" + url
        out["url"] = url[:2000]
    elif a == "search":
        q = str(cmd.get("query", "")).strip()
        if not q:
            return None
        out["url"] = "https://www.google.com/search?q=" + quote_plus(q[:300])
        out["action"] = "open_url"
    elif a == "scroll":
        d = cmd.get("dir")
        if d not in ("up", "down", "top", "bottom"):
            return None
        out["dir"] = d
    elif a in ("click", "switch_tab"):
        t = str(cmd.get("text", "")).strip()
        if not t:
            return None
        out["text"] = t[:120]
    elif a == "page_text":
        out["question"] = str(cmd.get("question", ""))[:500]
    return out


class Bridge:
    def __init__(self, ask_fn=None, reply_fn=None, port: int = PORT, store: Path | None = None, count_fn=None):
        self.blocked_sites: list[str] = []      # Karen mode: sites the extension must block
        self.count_fn = count_fn      # count_fn(site, n) -> today's total; called when the extension counts shorts
        self.ask_fn = ask_fn          # ask_fn(question, page) -> str   (runs on a worker thread)
        self.reply_fn = reply_fn      # reply_fn(text): shown/spoken in EV when a voice-started question is answered
        self.port = port
        self._store_path = store or _store()
        self._commands: "queue.Queue[dict]" = queue.Queue()
        self._server: ThreadingHTTPServer | None = None
        self._last_poll = 0.0
        self._pending_question: str | None = None
        self._fails, self._locked_until = 0, 0.0
        self._lock = threading.Lock()
        self.code = self._new_code()
        self._tokens = self._load_tokens()

    # ---------------------------------------------------------- pairing state
    @staticmethod
    def _new_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def new_code(self) -> str:
        self.code = self._new_code()
        return self.code

    def _load_tokens(self) -> list[str]:
        try:
            return list(json.loads(self._store_path.read_text(encoding="utf-8")).get("tokens", []))
        except Exception:
            return []

    def _save_tokens(self) -> None:
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(json.dumps({"tokens": self._tokens}), encoding="utf-8")
        except OSError:
            pass

    def forget_all(self) -> None:
        """Unpairs every browser."""
        self._tokens = []
        self._save_tokens()
        self.new_code()

    def pair(self, code: str) -> str | None:
        with self._lock:
            if time.time() < self._locked_until:
                return None
            if hmac.compare_digest(str(code).strip(), self.code):
                token = secrets.token_hex(24)
                self._tokens = (self._tokens + [token])[-3:]          # at most 3 browsers
                self._save_tokens()
                self._fails = 0
                self.code = self._new_code()                            # a code works once
                return token
            self._fails += 1
            if self._fails >= 5:
                self._locked_until, self._fails = time.time() + 60, 0
                self.code = self._new_code()
            return None

    def authorized(self, token: str) -> bool:
        return bool(token) and any(hmac.compare_digest(token, t) for t in self._tokens)

    @property
    def connected(self) -> bool:
        return time.time() - self._last_poll < CONNECTED_WITHIN_S

    # --------------------------------------------------------------- commands
    def send(self, cmd: dict) -> bool:
        safe = clean_command(cmd)
        if safe is None:
            return False
        self._commands.put(safe)
        return True

    def set_blocked_sites(self, sites) -> None:
        """Karen mode: websites the extension blocks in Chrome (plain domains only)."""
        self.blocked_sites = [d for d in (str(x).strip().lower() for x in sites)
                              if d and len(d) < 100 and re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d)][:100]

    def ask_about_page(self, question: str) -> None:
        """Voice: 'what is this page about'. The extension answers with the page text; EV replies via reply_fn."""
        self._pending_question = question
        self.send({"action": "page_text", "question": question})

    def _answer(self, question: str, page: dict) -> str:
        if not self.ask_fn:
            return "EV's AI isn't available right now."
        return self.ask_fn(question, page)

    # ----------------------------------------------------------------- server
    def start(self) -> bool:
        if self._server:
            return True
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):        # keep the console quiet
                pass

            def _ok_origin(self) -> bool:
                host = (self.headers.get("Host") or "").split(":")[0]
                origin = self.headers.get("Origin") or ""
                return host in ("127.0.0.1", "localhost") and (not origin or origin.startswith("chrome-extension://"))

            def _send(self, code: int, obj: dict):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    raise ValueError("too large")
                return json.loads(self.rfile.read(n) or b"{}")

            def _auth(self) -> bool:
                return bridge.authorized(self.headers.get("X-EV-Token", ""))

            def do_OPTIONS(self):             # extension pre-flight
                if not self._ok_origin():
                    return self._send(403, {"error": "forbidden"})
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-EV-Token")
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                if not self._ok_origin():
                    return self._send(403, {"error": "forbidden"})
                if self.path.startswith("/ping"):
                    return self._send(200, {"ok": True, "app": "EV AI"})
                if self.path.startswith("/rules"):
                    if not self._auth():
                        return self._send(401, {"error": "not paired"})
                    return self._send(200, {"blocked_sites": list(bridge.blocked_sites)})
                if self.path.startswith("/poll"):
                    if not self._auth():
                        return self._send(401, {"error": "not paired"})
                    bridge._last_poll = time.time()
                    try:
                        cmd = bridge._commands.get(timeout=20)
                    except queue.Empty:
                        cmd = None
                    bridge._last_poll = time.time()
                    return self._send(200, {"command": cmd})
                self._send(404, {"error": "not found"})

            def do_POST(self):
                if not self._ok_origin():
                    return self._send(403, {"error": "forbidden"})
                try:
                    data = self._body()
                except Exception:
                    return self._send(400, {"error": "bad request"})
                if self.path == "/pair":
                    token = bridge.pair(str(data.get("code", "")))
                    return self._send(200, {"token": token}) if token else self._send(403, {"error": "wrong or locked"})
                if not self._auth():
                    return self._send(401, {"error": "not paired"})
                if self.path == "/ask":                           # typed in the extension popup
                    q, page = str(data.get("question", ""))[:1000], data.get("page") or {}
                    try:
                        return self._send(200, {"answer": bridge._answer(q, page)})
                    except Exception as e:
                        return self._send(200, {"answer": f"Sorry, that failed: {e}"})
                if self.path == "/page":                          # page text for a voice-started question
                    q = bridge._pending_question or "What is this page about?"
                    bridge._pending_question = None
                    page = data.get("page") or {}
                    self._send(200, {"ok": True})
                    threading.Thread(target=bridge._voice_answer, args=(q, page), daemon=True).start()
                    return
                if self.path == "/count":                         # short videos scrolled (YouTube Shorts, Reels, TikTok)
                    site, n = str(data.get("site", ""))[:20], data.get("n", 1)
                    if bridge.count_fn is None or not isinstance(n, int) or not 1 <= n <= 50:
                        return self._send(400, {"error": "bad request"})
                    return self._send(200, {"today": bridge.count_fn(site, n)})
                self._send(404, {"error": "not found"})

        try:
            self._server = ThreadingHTTPServer((HOST, self.port), Handler)
        except OSError:
            return False                    # port busy (another EV AI is running)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return True

    def _voice_answer(self, question: str, page: dict) -> None:
        try:
            text = self._answer(question, page)
        except Exception as e:
            text = f"Sorry, I couldn't read that page: {e}"
        if self.reply_fn:
            self.reply_fn(text)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def page_prompt(question: str, page: dict) -> str:
    """The text sent to the AI: the question plus the page the user chose to share."""
    title, url = str(page.get("title", ""))[:200], str(page.get("url", ""))[:300]
    text = str(page.get("text", ""))[:12000]
    return (f"The user is looking at a web page and asks: {question}\n\n"
            f"PAGE TITLE: {title}\nPAGE URL: {url}\nPAGE TEXT (may be cut short):\n{text}\n\n"
            "Answer using the page. If the page doesn't contain the answer, say so. Keep it short and clear.")


_instance: Bridge | None = None


def get() -> Bridge | None:
    return _instance


def create(ask_fn=None, reply_fn=None, count_fn=None) -> Bridge:
    global _instance
    if _instance is None:
        _instance = Bridge(ask_fn, reply_fn, count_fn=count_fn)
    return _instance
