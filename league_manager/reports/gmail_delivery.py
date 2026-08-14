"""Gmail report delivery modes: dry-run, draft, send (mixin)."""

import logging
from email.mime.multipart import MIMEMultipart

from league_manager.reports.base import ReportContext, ReportResult
from league_manager.reports.gmail_compose import (
    write_draft_eml,
    write_dry_run_preview,
)

logger = logging.getLogger(__name__)


class GmailDeliveryMixin:
    """Mode-specific delivery of a composed report message."""

    async def _dry_run(self, context: ReportContext, message: MIMEMultipart) -> ReportResult:
        """Dry-run: save message preview without sending."""
        preview_file = context.game_dir / f"{context.game_id}_email_preview.txt"
        write_dry_run_preview(message, preview_file)
        logger.info(f"Dry-run preview saved to {preview_file}")
        return ReportResult(
            plugin=self.name,
            ok=True,
            status="dry_run",
            destination=str(preview_file),
            details={"mode": "dry_run", "recipient": self.recipient},
        )

    async def _draft(self, context: ReportContext, message: MIMEMultipart) -> ReportResult:
        """Draft mode: save message as .eml file."""
        eml_file = context.game_dir / f"{context.game_id}.eml"
        write_draft_eml(message, eml_file)
        logger.info(f"Draft email saved to {eml_file}")
        return ReportResult(
            plugin=self.name,
            ok=True,
            status="draft",
            destination=str(eml_file),
            details={"mode": "draft", "recipient": self.recipient},
        )

    async def _send(self, context: ReportContext, message: MIMEMultipart) -> ReportResult:
        """Send mode: send via Gmail API using stored OAuth token."""
        if not self.token_path.exists():
            logger.error(f"Gmail token not found: {self.token_path}")
            return ReportResult(
                plugin=self.name,
                ok=False,
                status="failed",
                error=f"Gmail OAuth token missing at {self.token_path}",
                error_code="gmail_auth_missing",
            )

        try:
            from league_manager.reports import gmail_report as _gr

            creds = _gr.load_oauth_credentials(self.token_path)
        except RuntimeError as auth_err:
            return ReportResult(
                plugin=self.name,
                ok=False,
                status="failed",
                error=str(auth_err),
                error_code="gmail_auth_missing",
            )
        except Exception as refresh_err:
            return ReportResult(
                plugin=self.name,
                ok=False,
                status="failed",
                error=(
                    "Gmail token refresh failed "
                    f"(re-authorize with scripts/gmail_auth.py): {refresh_err}"
                ),
                error_code="gmail_auth_missing",
            )

        try:
            message_id = _gr.gmail_api_send(message, creds)
            logger.info(f"Email sent to {self.recipient}, message_id={message_id}")
            return ReportResult(
                plugin=self.name,
                ok=True,
                status="sent",
                destination=self.recipient,
                details={"mode": "send", "message_id": message_id},
            )
        except Exception as e:
            logger.error(f"Gmail API send failed: {e}", exc_info=True)
            return ReportResult(
                plugin=self.name,
                ok=False,
                status="failed",
                error=str(e),
                error_code="gmail_send_error",
            )
