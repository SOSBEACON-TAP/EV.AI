"""
ui/accounts_dialog.py
-----------------------
Settings -> "AI, email & voice": change the AI provider and API key, the
email account EV.AI sends from (Outlook, Gmail, or any SMTP provider), and
a few voice options — all without hand-editing the .env file. Saving
writes to .env (core/env_file.py keeps your comments and other settings
untouched).

config.Config reads the environment once at startup, so a restart is
needed to apply changes; after saving, this offers one.

Secrets (API key, app password) are never shown back: the fields start
empty with a "saved" placeholder, and leaving one empty keeps what's
already stored.
"""

import os
import smtplib
import subprocess
import sys
import urllib.error
import urllib.request
from email.mime.text import MIMEText

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from config import settings, APP_ROOT
from core.env_file import update_env, read_value
from core import user_prefs
from ui.theme import dialog_stylesheet

_PROVIDERS = [
    ("Anthropic (Claude)", "anthropic", "claude-sonnet-4-6"),
    ("Google Gemini", "gemini", "gemini-3.8-flash"),
    ("Groq", "groq", "openai/gpt-oss-120b"),
    ("OpenAI (ChatGPT)", "openai", "gpt-4o"),
    ("OpenRouter (many models)", "openrouter", "openai/gpt-4o"),
    ("DeepSeek", "deepseek", "deepseek-chat"),
    ("Mistral", "mistral", "mistral-large-latest"),
    ("xAI (Grok)", "xai", "grok-4"),
    ("Custom (OpenAI-compatible / Ollama)", "custom", ""),
]

# label, host, port
_EMAIL_SERVICES = [
    ("Outlook / Microsoft 365", "smtp-mail.outlook.com", "587"),
    ("Gmail", "smtp.gmail.com", "465"),
    ("Other (enter host and port)", "", ""),
]


class _TaskWorker(QThread):
    """Runs a blocking check (network/SMTP) off the GUI thread."""
    done = Signal(bool, str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            ok, message = self._fn()
        except Exception as e:
            ok, message = False, f"{type(e).__name__}: {e}"
        self.done.emit(ok, message)


_KEY_CHECK_URLS = {
    "anthropic": ("https://api.anthropic.com/v1/models",
                  lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"}),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models",
               lambda key: {"x-goog-api-key": key}),
    "groq": ("https://api.groq.com/openai/v1/models",
             lambda key: {"Authorization": f"Bearer {key}"}),
}
for _p, _base in {
    "openai": "https://api.openai.com/v1", "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com", "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
}.items():
    _KEY_CHECK_URLS[_p] = (_base + "/models", lambda key: {"Authorization": f"Bearer {key}"})


def _check_api_key(provider: str, key: str, base_url: str = "") -> tuple[bool, str]:
    if provider == "custom":
        base = (base_url or "").rstrip("/")
        if not base:
            return False, "Enter the server address (base URL) first."
        url, make_headers = base + "/models", (lambda key: {"Authorization": f"Bearer {key}"})
    else:
        url, make_headers = _KEY_CHECK_URLS[provider]
    headers = make_headers(key)
    headers["User-Agent"] = "EV.AI"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status == 200:
                return True, "That API key works."
            return False, f"Unexpected response ({response.status})."
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403):
            return False, "The provider rejected that key — double-check it and the provider."
        return False, f"The provider returned an error ({e.code})."
    except OSError as e:
        return False, f"Couldn't reach the provider — check your internet. ({e})"


def _send_test_email(host: str, port: int, address: str, password: str) -> tuple[bool, str]:
    message = MIMEText("This is a test email from EV.AI. Your email settings work.")
    message["Subject"] = "EV.AI test email"
    message["From"] = address
    message["To"] = address
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        try:
            server.login(address, password)
            server.send_message(message)
        finally:
            try:
                server.quit()
            except smtplib.SMTPException:
                pass
    except smtplib.SMTPAuthenticationError as e:
        reply = e.smtp_error.decode("utf-8", "replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        hint = "Check the address and the app password."
        if "5.7.139" in reply or "basic auth" in reply.lower() or "SmtpClientAuthentication" in reply:
            hint = ("Microsoft has turned off password sign-in for SMTP on this account — "
                    "use a Gmail address + Gmail app password instead.")
        elif host.endswith("gmail.com"):
            hint = "Gmail needs 2-Step Verification on, and a 16-letter app password (not your normal password)."
        return False, f"Login rejected ({e.smtp_code}). {hint}\n\nServer said: {reply[:300]}"
    except (smtplib.SMTPException, OSError) as e:
        return False, f"Couldn't send: {e}"
    return True, f"Sent! Check the inbox of {address}."


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "section")
    return label


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("role", "sub")
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("background: rgba(128,150,180,60); max-height: 1px; border: none;")
    return line


def _secret_field(has_saved: bool) -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.Password)
    field.setPlaceholderText("saved — leave blank to keep it" if has_saved else "not set")
    return field


class AccountsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{settings.APP_NAME} — AI, email & voice")
        self.setFixedWidth(420)
        self.setMaximumHeight(640)
        self.setStyleSheet(dialog_stylesheet(user_prefs.get("theme")))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        root = QVBoxLayout(body)
        root.setContentsMargins(20, 18, 20, 8)
        root.setSpacing(8)

        # -- AI ------------------------------------------------------------
        root.addWidget(_section("AI PROVIDER"))
        self._provider = QComboBox()
        current_provider = (settings.AI_PROVIDER or "anthropic").lower()
        for label, value, _default_model in _PROVIDERS:
            self._provider.addItem(label, value)
        index = self._provider.findData(current_provider)
        self._provider.setCurrentIndex(max(index, 0))
        self._initial_provider = self._provider.currentData()
        root.addWidget(self._provider)

        root.addWidget(QLabel("API key"))
        self._api_key = _secret_field(bool(settings.AI_API_KEY))
        root.addWidget(self._api_key)

        root.addWidget(QLabel("Model"))
        self._model = QLineEdit(settings.AI_MODEL)
        root.addWidget(self._model)
        self._base_url_label = QLabel("Server address (base URL)")
        self._base_url = QLineEdit(settings.AI_BASE_URL)
        self._base_url.setPlaceholderText("http://localhost:11434/v1")
        root.addWidget(self._base_url_label)
        root.addWidget(self._base_url)
        self._provider.currentIndexChanged.connect(self._on_provider_changed)
        self._update_base_url_visibility()
        root.addWidget(_note(
            "Changing provider fills in that provider's default model, and "
            "needs that provider's API key."
        ))
        self._check_key_btn = QPushButton("Check API key")
        self._check_key_btn.clicked.connect(self._on_check_key)
        root.addWidget(self._check_key_btn)

        root.addWidget(_divider())

        # -- Email ---------------------------------------------------------
        root.addWidget(_section("EMAIL ACCOUNT (for sending email)"))
        self._service = QComboBox()
        for label, _host, _port in _EMAIL_SERVICES:
            self._service.addItem(label)
        self._service.setCurrentIndex(self._guess_service())
        self._service.currentIndexChanged.connect(self._on_service_changed)
        root.addWidget(self._service)

        root.addWidget(QLabel("Email address (your Outlook ID)"))
        self._email = QLineEdit(settings.EMAIL_ADDRESS)
        self._email.setPlaceholderText("you@outlook.com")
        root.addWidget(self._email)

        root.addWidget(QLabel("App password"))
        self._email_password = _secret_field(bool(settings.EMAIL_APP_PASSWORD))
        root.addWidget(self._email_password)

        host_row = QHBoxLayout()
        self._host = QLineEdit(settings.EMAIL_SMTP_HOST)
        self._port = QLineEdit(str(settings.EMAIL_SMTP_PORT))
        self._port.setFixedWidth(70)
        host_row.addWidget(self._host, 1)
        host_row.addWidget(self._port)
        root.addLayout(host_row)
        self._on_service_changed()  # lock/unlock the host+port boxes
        root.addWidget(_note(
            "Use an app password, not your normal account password. For "
            "Outlook: account.microsoft.com -> Security -> Advanced security "
            "options -> App passwords."
        ))

        self._test_email_btn = QPushButton("Send a test email to myself")
        self._test_email_btn.clicked.connect(self._on_test_email)
        root.addWidget(self._test_email_btn)

        root.addWidget(_divider())

        # -- Voice ---------------------------------------------------------
        root.addWidget(_section("VOICE"))
        root.addWidget(QLabel("Wake word"))
        self._wake = QLineEdit(settings.WAKE_WORD)
        root.addWidget(self._wake)

        root.addWidget(QLabel("Speech engine"))
        self._tts = QComboBox()
        self._tts.addItem("Offline (pyttsx3)", "pyttsx3")
        self._tts.addItem("Natural voice (Edge, needs internet)", "edge")
        self._tts.setCurrentIndex(1 if (settings.TTS_PROVIDER or "").lower() == "edge" else 0)
        root.addWidget(self._tts)

        root.addWidget(QLabel("Edge voice name"))
        self._edge_voice = QLineEdit(settings.EDGE_TTS_VOICE)
        root.addWidget(self._edge_voice)
        self._preview_btn = QPushButton("▶ Preview this voice (without saving)")
        self._preview_btn.clicked.connect(self._on_preview_voice)
        root.addWidget(self._preview_btn)

        # -- buttons -------------------------------------------------------
        buttons = QHBoxLayout()
        buttons.setContentsMargins(20, 0, 20, 0)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        outer.addLayout(buttons)

    # -- helpers ------------------------------------------------------------
    def _guess_service(self) -> int:
        host = (settings.EMAIL_SMTP_HOST or "").lower()
        for i, (_label, svc_host, _port) in enumerate(_EMAIL_SERVICES):
            if svc_host and svc_host == host:
                return i
        return len(_EMAIL_SERVICES) - 1

    def _update_base_url_visibility(self) -> None:
        show = self._provider.currentData() == "custom"
        self._base_url_label.setVisible(show)
        self._base_url.setVisible(show)

    def _on_provider_changed(self) -> None:
        self._update_base_url_visibility()
        provider = self._provider.currentData()
        for _label, value, default_model in _PROVIDERS:
            if value == provider:
                self._model.setText(default_model)

    def _on_service_changed(self) -> None:
        _label, host, port = _EMAIL_SERVICES[self._service.currentIndex()]
        custom = not host
        if not custom:
            self._host.setText(host)
            self._port.setText(port)
        self._host.setEnabled(custom)
        self._port.setEnabled(custom)

    # -- voice preview --------------------------------------------------------
    def _on_preview_voice(self) -> None:
        engine = self._tts.currentData()
        voice = self._edge_voice.text().strip() or "en-US-JennyNeural"
        sample = "Hello, I'm EV. This is how I'll sound."

        def _speak() -> tuple[bool, str]:
            if engine == "edge":
                from voice.edge_tts_backend import EdgeTTS, EdgeTTSError
                try:
                    EdgeTTS(voice=voice, rate=settings.EDGE_TTS_RATE).speak(sample)
                    return True, ""
                except EdgeTTSError as e:
                    return False, f"The natural voice isn't available: {e}"
            from voice.text_to_speech import TextToSpeech
            TextToSpeech(voice_gender=settings.TTS_VOICE).speak(sample)
            return True, ""

        self._preview_btn.setEnabled(False)
        self._preview_btn.setText("Playing…")
        self._voice_worker = _TaskWorker(_speak, self)

        def _finished(ok: bool, message: str) -> None:
            self._preview_btn.setEnabled(True)
            self._preview_btn.setText("▶ Preview this voice (without saving)")
            if not ok:
                QMessageBox.warning(self, "Voice preview", message)

        self._voice_worker.done.connect(_finished)
        self._voice_worker.start()

    # -- checks ---------------------------------------------------------------
    def _run_check(self, button: QPushButton, title: str, fn) -> None:
        button.setEnabled(False)
        original = button.text()
        button.setText("Checking…")
        self._worker = _TaskWorker(fn, self)

        def _finished(ok: bool, message: str) -> None:
            button.setEnabled(True)
            button.setText(original)
            (QMessageBox.information if ok else QMessageBox.warning)(self, title, message)

        self._worker.done.connect(_finished)
        self._worker.start()

    def _on_check_key(self) -> None:
        provider = self._provider.currentData()
        key = self._api_key.text().strip()
        if not key and provider == self._initial_provider:
            key = settings.AI_API_KEY
        if not key:
            QMessageBox.warning(self, "Check API key", "Enter an API key first.")
            return
        self._run_check(self._check_key_btn, "Check API key", lambda: _check_api_key(provider, key, self._base_url.text().strip()))

    def _on_test_email(self) -> None:
        address = self._email.text().strip()
        password = "".join((self._email_password.text() or settings.EMAIL_APP_PASSWORD).split())
        port = self._port.text().strip()
        if not address or not password or not port.isdigit():
            QMessageBox.warning(
                self, "Test email",
                "Fill in the email address, app password and a numeric port first.",
            )
            return
        host = self._host.text().strip()
        self._run_check(
            self._test_email_btn, "Test email",
            lambda: _send_test_email(host, int(port), address, password),
        )

    # -- save -----------------------------------------------------------------
    def _on_save(self) -> None:
        provider = self._provider.currentData()
        provider_changed = provider != self._initial_provider
        new_key = self._api_key.text().strip()
        if provider_changed and not new_key:
            QMessageBox.warning(
                self, "API key needed",
                "You changed the provider, so enter an API key for the new one "
                "(the saved key belongs to the old provider).",
            )
            return

        port = self._port.text().strip()
        if not port.isdigit():
            QMessageBox.warning(self, "Email port", "The email port should be a number, like 587 or 465.")
            return

        updates: dict[str, str | None] = {
            "AI_PROVIDER": provider,
            "AI_BASE_URL": (self._base_url.text().strip() or None) if provider == "custom" else None,
            "AI_MODEL": self._model.text().strip() or None,
            "EMAIL_ADDRESS": self._email.text().strip(),
            "EMAIL_SMTP_HOST": self._host.text().strip(),
            "EMAIL_SMTP_PORT": port,
            "WAKE_WORD": self._wake.text().strip() or "hey ev",
            "TTS_PROVIDER": self._tts.currentData(),
            "EDGE_TTS_VOICE": self._edge_voice.text().strip() or "en-US-JennyNeural",
        }
        if new_key:
            updates["AI_API_KEY"] = new_key
        new_email_password = self._email_password.text().strip()
        if new_email_password:
            updates["EMAIL_APP_PASSWORD"] = "".join(new_email_password.split())
        if provider_changed:
            # A vision model set for the old provider won't exist on the new
            # one — drop it so the new provider's default is used.
            updates["AI_VISION_MODEL"] = None

        try:
            update_env(updates)
        except OSError as e:
            QMessageBox.warning(self, "Couldn't save", f"Writing the .env file failed: {e}")
            return

        answer = QMessageBox.question(
            self, "Saved",
            "Saved. These apply after a restart — restart EV.AI now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        self.accept()
        if answer == QMessageBox.Yes:
            _restart_app()


def _restart_app() -> None:
    """Starts a fresh copy of EV.AI, then closes this one."""
    if getattr(sys, "frozen", False):
        command = [sys.executable]
    else:
        command = [sys.executable, str(APP_ROOT / "main.py")]
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(command, cwd=str(APP_ROOT), creationflags=flags, close_fds=True)
    except OSError as e:
        QMessageBox.warning(None, "Restart", f"Couldn't restart automatically ({e}). Please start EV.AI again yourself.")
        return
    app = QApplication.instance()
    for widget in app.topLevelWidgets():
        if hasattr(widget, "allow_close"):
            widget.allow_close()
    app.closeAllWindows()
    QTimer.singleShot(0, app.quit)
