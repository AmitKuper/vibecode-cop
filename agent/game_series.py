"""Six-gamelet series runner using GameRunner — LOCAL SIMULATOR ONLY.

GameRunner is a central coordinator that drives both agents in-process.
It does NOT satisfy the no-central-judge P2P production requirement.

For production P2P series, use scripts/run_series.py which drives gamelets
via cop PeerRuntime calling the thief's MCP endpoint directly.
"""

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
    try:
        from agent.config.shared_config import load_shared_config

        return load_shared_config().get("scoring", {})
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
        sc = _load_scoring()
        pts_matrix = {
            "cop": (sc.get("capture_cop", 20), sc.get("capture_thief", 5)),
            "thief": (sc.get("survival_cop", 5), sc.get("survival_thief", 10)),
        }
        tie_pts = sc.get("tie_score", 2)
        gamelets: list[dict] = []
        cop_total = thief_total = 0
        for idx in range(1, self.n_gamelets + 1):
            lbl = f"g{idx:02d}"
            game_id = f"{series_id}_{lbl}"
            logger.info(f"[GameSeries] Running gamelet {lbl} ({game_id})")
            try:
                result = await self._make_runner().run_game(game_id=game_id)
                winner = result.get("winner", "unknown")
                audit_ok = result.get("audit_ok", False)
                if winner == "TECHNICAL_LOSS" or not audit_ok:
                    cop_pts = thief_pts = 0
                elif winner in pts_matrix:
                    cop_pts, thief_pts = pts_matrix[winner]
                else:
                    cop_pts = thief_pts = tie_pts
                cop_total += cop_pts
                thief_total += thief_pts
                rec = {
                    "gamelet": lbl,
                    "game_id": game_id,
                    "winner": winner,
                    "audit_ok": audit_ok,
                    "cop_pts": cop_pts,
                    "thief_pts": thief_pts,
                    "final_step": result.get("final_step"),
                }
            except Exception as exc:
                logger.error(f"[GameSeries] Gamelet {lbl} failed: {exc}", exc_info=True)
                rec = {
                    "gamelet": lbl,
                    "game_id": game_id,
                    "winner": "error",
                    "audit_ok": False,
                    "cop_pts": 0,
                    "thief_pts": 0,
                    "error": str(exc),
                }
            gamelets.append(rec)
            logger.info(
                f"[GameSeries] Gamelet {lbl}: winner={rec['winner']} "
                f"cop+={rec['cop_pts']} thief+={rec['thief_pts']}"
            )

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
        out_path = self.games_dir / f"result_{series_id}_series.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(series_result, indent=2), encoding="utf-8")
        logger.info(
            f"[GameSeries] Series {series_id} complete: {series_winner} wins "
            f"(cop {cop_total} – thief {thief_total})"
        )
        return series_result
