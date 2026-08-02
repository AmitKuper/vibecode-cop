"""Build report context and collect required/optional game files."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.reports.base import ReportContext

logger = logging.getLogger(__name__)


class ReportBundleBuilder:
    """Collects required and optional game files into a ReportContext."""

    def __init__(self, game_dir: Path):
        self.game_dir = Path(game_dir)

    async def build(
        self,
        game_id: str,
        role: str,
        game_state: dict,
        result: dict | None = None,
        config_hash: str | None = None,
        log_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReportContext:
        """Build complete report context with all files."""

        # Ensure required files exist (create empty stubs if missing)
        required = await self._ensure_required_files(game_id)

        # Collect optional files if they exist
        optional = self._collect_optional_files()

        # Build context
        context = ReportContext(
            game_id=game_id,
            role=role,
            group_id=metadata.get("group_id", "unknown") if metadata else "unknown",
            opponent_group_id=metadata.get("opponent_group_id") if metadata else None,
            game_dir=self.game_dir,
            game_state=game_state,
            result=result,
            start_timestamp=game_state.get("created_at", datetime.now().isoformat()),
            end_timestamp=game_state.get("ended_at", datetime.now().isoformat()),
            config_hash=config_hash,
            log_hash=log_hash,
            required_files=required,
            optional_files=optional,
            metadata=metadata or {},
        )

        logger.info(
            f"Built report context for {game_id}: "
            f"{len(required)} required, {len(optional)} optional files"
        )

        return context

    async def _ensure_required_files(self, game_id: str) -> dict[str, Path]:
        """Return paths to required files; raise FileNotFoundError if any are missing."""

        # Discover actual gamelet suffix (g01, g02, …) — do not hardcode g00
        config_candidates = sorted(self.game_dir.glob(f"config_{game_id}_g*.json"))
        log_candidates = sorted(self.game_dir.glob(f"log_{game_id}_g*.json"))

        required = {
            "declaration": self.game_dir / f"declaration_{game_id}.json",
            "config": (
                config_candidates[0]
                if config_candidates
                else self.game_dir / f"config_{game_id}_g01.json"
            ),
            "log": (
                log_candidates[0] if log_candidates else self.game_dir / f"log_{game_id}_g01.json"
            ),
            "result": self.game_dir / f"result_{game_id}.json",
        }

        missing = [str(path) for path in required.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                f"Required report files missing for {game_id}: {missing}. "
                "GameRunner must write real files before triggering reports."
            )

        return required

    def _collect_optional_files(self) -> dict[str, Path]:
        """Collect optional files if they exist."""

        optional_names = ["report.json", "report.md", "moves.jsonl", "game_state.json"]
        optional = {}

        for name in optional_names:
            path = self.game_dir / name
            if path.exists():
                optional[name] = path
                logger.debug(f"Found optional file: {name}")

        return optional
