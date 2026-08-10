"""Gmail API report plugin with OAuth 2.0."""

import logging
from pathlib import Path

from league_manager.reports.base import ReportContext, ReportResult
from league_manager.reports.gmail_compose import (
    attach_file,
    build_email_message,
    collect_attachments,
)

from league_manager.reports.gmail_delivery import GmailDeliveryMixin
from league_manager.reports.gmail_send import (  # noqa: F401  (patchable seams)
    gmail_api_send,
    load_oauth_credentials,
)

logger = logging.getLogger(__name__)


class GmailReportPlugin(GmailDeliveryMixin):
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
                plugin=self.name,
                ok=False,
                status="failed",
                error=str(e),
                error_code="gmail_error",
            )
