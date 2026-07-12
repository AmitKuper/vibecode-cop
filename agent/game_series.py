"""Six-gamelet series runner — runs N gamelets and aggregates scores."""

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from agent.game_runner import GameRunner

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_scoring() -> dict:
    """Load scoring values from shared config with safe defaults."""
    try:
        from agent.config.shared_config import load_shared_config
        cfg = load_shared_config()
        return cfg.get("scoring", {})
    except Exception:
        return {}


class GameSeries:
    """Runs a fixed number of gamelets and aggregates scores into a series result."""

    def __init__(
        self,
        cop_url: str = "http://localhost:5000",
        thief_url: str = "http://localhost:5001",
        secret: str = "dev-secret-change-me",
        config_sha256: str = "a" * 64,
        games_dir: Path = Path("agent/memory"),
        max_turns: int = 35,
        group_name: str = "unknown",
        n_gamelets: int = 6,
    ):
        self.cop_url = cop_url
        self.thief_url = thief_url
        self.secret = secret
        self.config_sha256 = config_sha256
        self.games_dir = Path(games_dir)
        self.max_turns = max_turns
        self.group_name = group_name
        self.n_gamelets = n_gamelets

    def _make_runner(self) -> GameRunner:
        return GameRunner(
            cop_url=self.cop_url,
            thief_url=self.thief_url,
            secret=self.secret,
            config_sha256=self.config_sha256,
            games_dir=self.games_dir,
            max_turns=self.max_turns,
            group_name=self.group_name,
        )

    async def run_series(self, series_id: str | None = None) -> dict:
        """Run n_gamelets gamelets sequentially and return aggregated series result."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        series_id = series_id or f"series_{ts}_{uuid.uuid4().hex[:8]}"
        started_at = _now_iso()
        logger.info(f"[GameSeries] Starting series {series_id} ({self.n_gamelets} gamelets)")

        scoring = _load_scoring()
        capture_cop = scoring.get("capture_cop", 20)
        capture_thief = scoring.get("capture_thief", 5)
        survival_cop = scoring.get("survival_cop", 5)
        survival_thief = scoring.get("survival_thief", 10)
        tie_score = scoring.get("tie_score", 2)

        gamelets: list[dict] = []
        cop_total = 0
        thief_total = 0

        for idx in range(1, self.n_gamelets + 1):
            gamelet_label = f"g{idx:02d}"
            game_id = f"{series_id}_{gamelet_label}"
            logger.info(f"[GameSeries] Running gamelet {gamelet_label} ({game_id})")
            try:
                runner = self._make_runner()
                result = await runner.run_game(game_id=game_id)
                winner = result.get("winner", "unknown")
                audit_ok = result.get("audit_ok", False)

                if winner == "TECHNICAL_LOSS" or not audit_ok:
                    cop_pts = 0
                    thief_pts = 0
                elif winner == "cop":
                    cop_pts = capture_cop
                    thief_pts = capture_thief
                elif winner == "thief":
                    cop_pts = survival_cop
                    thief_pts = survival_thief
                else:
                    # tie
                    cop_pts = tie_score
                    thief_pts = tie_score

                cop_total += cop_pts
                thief_total += thief_pts
                gamelet_record = {
                    "gamelet": gamelet_label,
                    "game_id": game_id,
                    "winner": winner,
                    "audit_ok": audit_ok,
                    "cop_pts": cop_pts,
                    "thief_pts": thief_pts,
                    "final_step": result.get("final_step"),
                }
            except Exception as exc:
                logger.error(f"[GameSeries] Gamelet {gamelet_label} failed: {exc}", exc_info=True)
                gamelet_record = {
                    "gamelet": gamelet_label,
                    "game_id": game_id,
                    "winner": "error",
                    "audit_ok": False,
                    "cop_pts": 0,
                    "thief_pts": 0,
                    "error": str(exc),
                }

            gamelets.append(gamelet_record)
            logger.info(
                f"[GameSeries] Gamelet {gamelet_label}: winner={gamelet_record['winner']} "
                f"cop+={gamelet_record['cop_pts']} thief+={gamelet_record['thief_pts']}"
            )

        # Determine series winner
        if cop_total > thief_total:
            series_winner = "cop"
        elif thief_total > cop_total:
            series_winner = "thief"
        else:
            series_winner = "tie"

        series_result = {
            "series_id": series_id,
            "config_sha256": self.config_sha256,
            "n_gamelets": self.n_gamelets,
            "gamelets": gamelets,
            "cop_total": cop_total,
            "thief_total": thief_total,
            "series_winner": series_winner,
            "started_at": started_at,
            "ended_at": _now_iso(),
        }

        # Write series result file
        out_path = self.games_dir / f"result_{series_id}_series.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(series_result, indent=2), encoding="utf-8")
        logger.info(
            f"[GameSeries] Series {series_id} complete: {series_winner} wins "
            f"(cop {cop_total} – thief {thief_total})"
        )
        return series_result
