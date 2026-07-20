"""Gmail API report plugin with OAuth 2.0."""

import logging
from email.mime.multipart import MIMEMultipart
from pathlib import Path

from agent.reports.base import ReportContext, ReportResult
from agent.reports.gmail_compose import (
    attach_file,
    build_email_message,
    collect_attachments,
    write_draft_eml,
    write_dry_run_preview,
)
from agent.reports.gmail_send import gmail_api_send, load_oauth_credentials

logger = logging.getLogger(__name__)


class GmailReportPlugin:
    """Send game reports via Gmail API with OAuth 2.0."""

    def __init__(
        self,
        name: str = "gmail",
        mode: str = "dry_run",
        recipient: str = "example@example.com",
        credentials_path: str | Path = "secrets/gmail/credentials.json",
        token_path: str | Path = "secrets/gmail/token.json",
        attach_required_files: bool = True,
        attach_markdown_summary: bool = True,
        max_attachments_mb: int = 20,
    ):
        """Initialize Gmail report plugin (mode: disabled|dry_run|draft|send)."""
        self.name = name
        self.mode = mode
        self.recipient = recipient
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.attach_required_files = attach_required_files
        self.attach_markdown_summary = attach_markdown_summary
        self.max_attachments_mb = max_attachments_mb

    async def generate(self, context: ReportContext) -> ReportResult:
        """Generate and send (or preview) Gmail report."""
        if self.mode == "disabled":
            logger.info(f"Gmail plugin {self.name} is disabled")
            return ReportResult(plugin=self.name, ok=True, status="skipped")

        try:
            message = build_email_message(context, self.recipient, self.mode)
            for filename, filepath in collect_attachments(
                context, self.attach_required_files, self.attach_markdown_summary
            ).items():
                attach_file(message, filename, filepath)

            if self.mode == "dry_run":
                return await self._dry_run(context, message)
            elif self.mode == "draft":
                return await self._draft(context, message)
            elif self.mode == "send":
                return await self._send(context, message)
            return ReportResult(
                plugin=self.name,
                ok=False,
                status="failed",
                error=f"Unknown mode: {self.mode}",
                error_code="invalid_mode",
            )

        except Exception as e:
            logger.error(f"Gmail plugin {self.name} failed: {e}", exc_info=True)
            return ReportResult(
                plugin=self.name, ok=False, status="failed",
                error=str(e), error_code="gmail_error",
            )

    async def _dry_run(
        self, context: ReportContext, message: MIMEMultipart
    ) -> ReportResult:
        """Dry-run: save message preview without sending."""
        preview_file = context.game_dir / f"{context.game_id}_email_preview.txt"
        write_dry_run_preview(message, preview_file)
        logger.info(f"Dry-run preview saved to {preview_file}")
        return ReportResult(
            plugin=self.name, ok=True, status="dry_run",
            destination=str(preview_file),
            details={"mode": "dry_run", "recipient": self.recipient},
        )

    async def _draft(
        self, context: ReportContext, message: MIMEMultipart
    ) -> ReportResult:
        """Draft mode: save message as .eml file."""
        eml_file = context.game_dir / f"{context.game_id}.eml"
        write_draft_eml(message, eml_file)
        logger.info(f"Draft email saved to {eml_file}")
        return ReportResult(
            plugin=self.name, ok=True, status="draft",
            destination=str(eml_file),
            details={"mode": "draft", "recipient": self.recipient},
        )

    async def _send(
        self, context: ReportContext, message: MIMEMultipart
    ) -> ReportResult:
        """Send mode: send via Gmail API using stored OAuth token."""
        if not self.token_path.exists():
            logger.error(f"Gmail token not found: {self.token_path}")
            return ReportResult(
                plugin=self.name, ok=False, status="failed",
                error=f"Gmail OAuth token missing at {self.token_path}",
                error_code="gmail_auth_missing",
            )

        try:
            creds = load_oauth_credentials(self.token_path)
        except RuntimeError as auth_err:
            return ReportResult(
                plugin=self.name, ok=False, status="failed",
                error=str(auth_err), error_code="gmail_auth_missing",
            )
        except Exception as refresh_err:
            return ReportResult(
                plugin=self.name, ok=False, status="failed",
                error=(
                    "Gmail token refresh failed "
                    f"(re-authorize with scripts/gmail_auth.py): {refresh_err}"
                ),
                error_code="gmail_auth_missing",
            )

        try:
            message_id = gmail_api_send(message, creds)
            logger.info(f"Email sent to {self.recipient}, message_id={message_id}")
            return ReportResult(
                plugin=self.name, ok=True, status="sent",
                destination=self.recipient,
                details={"mode": "send", "message_id": message_id},
            )
        except Exception as e:
            logger.error(f"Gmail API send failed: {e}", exc_info=True)
            return ReportResult(
                plugin=self.name, ok=False, status="failed",
                error=str(e), error_code="gmail_send_error",
            )
