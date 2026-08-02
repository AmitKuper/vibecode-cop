"""Email composition helpers: MIME construction, body, attachments, file output."""

import logging
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from agent.reports.base import ReportContext

logger = logging.getLogger(__name__)


def build_email_message(
    context: ReportContext,
    recipient: str,
    mode: str,
) -> MIMEMultipart:
    """Build MIME email message from game context (without attachments)."""
    message = MIMEMultipart()

    winner = (
        context.result.get("winner").upper()
        if context.result and context.result.get("winner")
        else "UNKNOWN"
    )
    subject = (
        f"Cop-Thief Game Report | {context.game_id}"
        f" | group={context.group_id}"
        f" | role={context.role}"
        f" | result={winner}"
    )
    message["Subject"] = subject
    message["From"] = "noreply@cop-thief-game.local"
    message["To"] = recipient

    body = build_email_body(context, mode)
    message.attach(MIMEText(body, "plain"))

    return message


def build_email_body(context: ReportContext, mode: str) -> str:
    """Build plain-text email body."""
    winner = (
        context.result.get("winner").upper()
        if context.result and context.result.get("winner")
        else "UNKNOWN"
    )

    return f"""Cop-Thief Game Report

Game ID: {context.game_id}
Group: {context.group_id}
Role: {context.role}
Opponent Group: {context.opponent_group_id or "Unknown"}

Result: {winner}
Start: {context.start_timestamp}
End: {context.end_timestamp}

Config Hash: {context.config_hash or "N/A"}
Log Hash: {context.log_hash or "N/A"}

Mode: {mode}
Attachments: See below

---
This is an automated report from the Cop-Thief game system.
"""


def collect_attachments(
    context: ReportContext,
    attach_required_files: bool,
    attach_markdown_summary: bool,
) -> dict[str, Path]:
    """Collect files to attach; returns filename -> Path for files that exist."""
    attachments: dict[str, Path] = {}

    if attach_required_files:
        for _name, path in context.required_files.items():
            if path.exists():
                attachments[path.name] = path

    if attach_markdown_summary and "report.md" in context.optional_files:
        attachments["report.md"] = context.optional_files["report.md"]

    return attachments


def attach_file(
    message: MIMEMultipart,
    filename: str,
    filepath: Path,
) -> None:
    """Attach a single file to a MIME message."""
    with open(filepath, "rb") as fh:
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(fh.read())

    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    message.attach(attachment)
    logger.debug(f"Attached file: {filename}")


def write_dry_run_preview(message: MIMEMultipart, preview_file: Path) -> None:
    """Write a human-readable email preview text file for dry-run mode."""
    preview_file.parent.mkdir(parents=True, exist_ok=True)

    with open(preview_file, "w") as fh:
        fh.write(f"Subject: {message['Subject']}\n")
        fh.write(f"From: {message['From']}\n")
        fh.write(f"To: {message['To']}\n")
        fh.write("\n--- BODY ---\n")
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                fh.write(part.get_payload(decode=True).decode())
                break
        fh.write("\n--- ATTACHMENTS ---\n")
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                fh.write(f"- {part.get_filename()}\n")


def write_draft_eml(message: MIMEMultipart, eml_file: Path) -> None:
    """Write message as a raw .eml file for draft mode."""
    eml_file.parent.mkdir(parents=True, exist_ok=True)

    with open(eml_file, "w") as fh:
        fh.write(message.as_string())
