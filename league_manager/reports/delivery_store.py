"""Persistent delivery history store."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DeliveryStore:
    """Persist report delivery history for idempotency."""

    def __init__(self, game_dir: Path):
        """Initialize delivery store.

        Args:
            game_dir: Game memory directory
        """
        self.game_dir = Path(game_dir)

    def get_delivery_path(self, game_id: str) -> Path:
        """Get path to delivery history file.

        Args:
            game_id: Game ID

        Returns:
            Path to report_delivery.json
        """
        return self.game_dir / game_id / "report_delivery.json"

    def load_history(self, game_id: str) -> list[dict]:
        """Load delivery history for a game.

        Args:
            game_id: Game ID

        Returns:
            List of delivery records (empty if file not found)
        """
        path = self.get_delivery_path(game_id)

        if not path.exists():
            logger.debug(f"No delivery history for {game_id}")
            return []

        try:
            with open(path) as f:
                data = json.load(f)
                return data.get("deliveries", [])
        except Exception as e:
            logger.error(f"Failed to load delivery history from {path}: {e}")
            return []

    async def record_delivery(self, game_id: str, record: dict) -> None:
        """Append delivery record to history.

        Args:
            game_id: Game ID
            record: Delivery record dict
        """
        path = self.get_delivery_path(game_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing
        history_data = {"game_id": game_id, "deliveries": self.load_history(game_id)}

        # Append new record
        history_data["deliveries"].append(record)

        # Save
        try:
            with open(path, "w") as f:
                json.dump(history_data, f, indent=2)
            logger.info(f"Recorded delivery to {path}")
        except Exception as e:
            logger.error(f"Failed to save delivery record to {path}: {e}")

    async def has_successful_delivery(self, game_id: str, plugin: str) -> bool:
        """Check if report was already successfully sent.

        Args:
            game_id: Game ID
            plugin: Plugin name

        Returns:
            True if previously sent
        """
        history = self.load_history(game_id)

        for record in history:
            if record.get("plugin") == plugin and record.get("status") == "sent":
                logger.debug(f"Found previous successful delivery: {game_id}/{plugin}")
                return True

        return False
