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
    """Build plain-text email cover note; the JSON attachment is the mandatory report."""
    winner = (
        context.result.get("winner").upper()
        if context.result and context.result.get("winner")
        else "UNKNOWN"
    )

    return (
        f"Automated match report from group {context.group_id} (role: {context.role}).\n\n"
        f"Game: {context.game_id}\n"
        f"Opponent: {context.opponent_group_id or 'unknown'}\n"
        f"Result: {winner}\n\n"
        f"The mandatory signed JSON report is attached as result_{context.game_id}.json.\n"
        f"Additional files (declaration, config, log) are also attached per §9.3.3.\n"
    )


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
