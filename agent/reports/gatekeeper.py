"""Gatekeeper for report delivery — prevent duplicate sends, enforce limits."""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ReportGatekeeper:
    """Guard against duplicate sends and enforce rate limits."""

    def __init__(
        self,
        max_sends_per_day: int = 10,
        min_interval_secs: int = 60,
        max_attachment_mb: int = 20,
        max_retries: int = 3,
    ):
        """Initialize gatekeeper.

        Args:
            max_sends_per_day: Daily send limit
            min_interval_secs: Minimum seconds between sends
            max_attachment_mb: Max attachment size
            max_retries: Max retry attempts
        """
        self.max_sends_per_day = max_sends_per_day
        self.min_interval_secs = min_interval_secs
        self.max_attachment_mb = max_attachment_mb
        self.max_retries = max_retries

    async def can_send(
        self,
        game_id: str,
        plugin: str,
        delivery_history: list[dict],
        mode: str = "send",
    ) -> tuple[bool, str]:
        """Check if sending is allowed.

        Args:
            game_id: Game ID
            plugin: Plugin name
            delivery_history: List of past delivery records
            mode: Send mode (send|dry_run|draft)

        Returns:
            (can_send, reason)
        """

        # In dry_run/draft, always allow (don't require real credentials)
        if mode in ("dry_run", "draft"):
            return True, "OK (non-send mode)"

        # Check idempotency: already sent for this game?
        for record in delivery_history:
            if (
                record.get("plugin") == plugin
                and record.get("status") == "sent"
                and record.get("game_id") == game_id
            ):
                logger.info(f"Report already sent for {game_id} via {plugin}")
                return False, "Already sent (idempotent)"

        # Check daily limit
        now = datetime.now()
        today_start = (now - timedelta(hours=24)).isoformat()
        sends_today = sum(
            1
            for r in delivery_history
            if r.get("status") == "sent"
            and r.get("timestamp", "") > today_start
        )

        if sends_today >= self.max_sends_per_day:
            logger.warning(f"Daily send limit reached ({self.max_sends_per_day})")
            return False, f"Daily limit reached ({sends_today}/{self.max_sends_per_day})"

        # Check retry count
        recent_failures = sum(
            1
            for r in delivery_history
            if r.get("status") == "failed"
            and r.get("game_id") == game_id
            and r.get("plugin") == plugin
        )

        if recent_failures >= self.max_retries:
            logger.warning(
                f"Max retries reached for {game_id}/{plugin} ({recent_failures})"
            )
            return (
                False,
                f"Max retries exceeded ({recent_failures}/{self.max_retries})",
            )

        return True, "OK"

    def record_send(
        self,
        game_id: str,
        plugin: str,
        mode: str,
        status: str,
        destination: str | None = None,
        message_id: str | None = None,
        error: str | None = None,
    ) -> dict:
        """Create a delivery record.

        Args:
            game_id: Game ID
            plugin: Plugin name
            mode: Send mode
            status: Result status (sent|skipped|failed)
            destination: Where it was sent
            message_id: Gmail message ID if applicable
            error: Error message if failed

        Returns:
            Record dict
        """

        record = {
            "game_id": game_id,
            "plugin": plugin,
            "mode": mode,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "destination": destination,
            "message_id": message_id,
            "error": error,
        }

        logger.info(
            f"Recording delivery: {game_id}/{plugin} -> {status} "
            f"({destination or 'N/A'})"
        )

        return record
