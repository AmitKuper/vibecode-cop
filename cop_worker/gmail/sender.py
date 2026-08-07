"""Process-constructible Gmail and explicitly fake acceptance senders."""

from __future__ import annotations

import hashlib
import json
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


class GmailApiSender:
    """Callable Gatekeeper dependency backed by Gmail OAuth."""

    def __init__(self, token_path: str | Path):
        self.token_path = Path(token_path)

    def validate(self) -> None:
        if not self.token_path.is_file():
            raise RuntimeError(f"Gmail OAuth token missing at {self.token_path}")
        token = json.loads(self.token_path.read_text(encoding="utf-8"))
        if not token.get("token") and not token.get("refresh_token"):
            raise RuntimeError("Gmail OAuth token has neither token nor refresh_token")

    def __call__(self, to: str, subject: str, body: str, attachments: list) -> str:
        from league_manager.reports.gmail_send import gmail_api_send, load_oauth_credentials

        message = MIMEMultipart()
        message["To"] = to
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))
        if attachments:
            raise RuntimeError("Gatekeeper Gmail sender does not accept untyped attachments")
        credentials = load_oauth_credentials(self.token_path)
        return gmail_api_send(message, credentials)


class AcceptanceFileGmailSender:
    """Explicit fake used only by local subprocess acceptance tests."""

    def __init__(self, outbox_path: str | Path):
        self.outbox_path = Path(outbox_path)
        self._lock = threading.Lock()

    def validate(self) -> None:
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        probe = self.outbox_path.parent / f".{self.outbox_path.name}.probe"
        probe.write_text("acceptance-only", encoding="utf-8")
        probe.unlink()

    def __call__(self, to: str, subject: str, body: str, attachments: list) -> str:
        digest = hashlib.sha256(f"{to}\0{subject}\0{body}".encode()).hexdigest()[:24]
        message_id = f"FAKE_ACCEPTANCE_GMAIL_{digest}"
        record = {
            "delivery_kind": "FAKE_ACCEPTANCE_ONLY",
            "message_id": message_id,
            "to": to,
            "subject": subject,
            "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "attachments": [str(item) for item in attachments],
        }
        with self._lock:
            self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
            with self.outbox_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        return message_id
