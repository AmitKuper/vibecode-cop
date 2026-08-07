"""Build report context and collect required/optional game files."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from league_manager.reports.base import ReportContext

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
        """Return paths to required files.

        Supports both GameRunner output (declaration/config/log/result) and
        PeerRuntime output (step0_evidence/journal/game_state/result).
        """
        gd = self.game_dir

        # Result file is required in both paths
        result_path = gd / f"result_{game_id}.json"

        # PeerRuntime path: step0_evidence + journal files instead of declaration/config/log
        step0 = gd / "step0_evidence.json"
        journal_candidates = sorted(gd.glob(f"journal_{game_id}_*.json"))
        game_state = gd / "game_state.json"

        if step0.exists() or journal_candidates:
            # PeerRuntime two-process path
            required: dict[str, Path] = {"result": result_path}
            if step0.exists():
                required["declaration"] = step0
            if journal_candidates:
                required["log"] = journal_candidates[0]
            if game_state.exists():
                required["config"] = game_state
            missing = [str(p) for p in required.values() if not p.exists()]
            if missing:
                raise FileNotFoundError(f"Required report files missing for {game_id}: {missing}.")
            return required

        # GameRunner legacy path: declaration/config/log/result
        config_candidates = sorted(gd.glob(f"config_{game_id}_g*.json"))
        log_candidates = sorted(gd.glob(f"log_{game_id}_g*.json"))
        required = {
            "declaration": gd / f"declaration_{game_id}.json",
            "config": (
                config_candidates[0] if config_candidates else gd / f"config_{game_id}_g01.json"
            ),
            "log": (log_candidates[0] if log_candidates else gd / f"log_{game_id}_g01.json"),
            "result": result_path,
        }
        missing = [str(p) for p in required.values() if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"Required report files missing for {game_id}: {missing}. "
                "GameRunner must write real files before triggering reports."
            )
        return required

    def _collect_optional_files(self) -> dict[str, Path]:
        """Collect optional files if they exist."""
        optional: dict[str, Path] = {}

        # Fixed-name optional files
        for name in [
            "report.json",
            "report.md",
            "moves.jsonl",
            "game_state.json",
            "step0_evidence.json",
            "my_commitments_cop.json",
            "my_commitments_thief.json",
        ]:
            path = self.game_dir / name
            if path.exists():
                optional[name] = path

        # Glob for journal files (PeerRuntime)
        for p in sorted(self.game_dir.glob("journal_*.json")):
            optional[p.name] = p

        return optional
