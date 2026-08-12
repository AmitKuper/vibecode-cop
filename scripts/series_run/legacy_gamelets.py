"""Unreachable legacy gamelet loop retained verbatim from run_series.py.

This is the first half of the original ``run_series`` body that sat below the
unconditional ``raise NotImplementedError`` (PeerRuntime was removed in the
Phase 1 restructure). It is NEVER called — kept for reference only, exactly as
it appeared inline, with the consumed locals promoted to parameters.
"""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from series_run.legacy_stubs import PeerRuntime
from series_run.tokens import _validated_token_totals

logger = logging.getLogger(__name__)


async def _legacy_run_gamelets(
    *,
    thief_url: str,
    secret: str,
    config_sha256: str,
    games_dir: Path,
    n_gamelets: int,
    group_name: str,
    llm_dict: dict | None,
    orchestrator_config: dict | None,
    mode,
    RuntimeMode,  # noqa: N803 — was the imported class name in the original body
    load_shared_config,
):
    """Never called — unreachable original body (gamelet loop half)."""
    shared_cfg = load_shared_config()  # noqa: E501
    scoring = shared_cfg.get("scoring", {})
    capture_cop = scoring.get("capture_cop", 20)
    capture_thief = scoring.get("capture_thief", 5)
    survival_cop = scoring.get("survival_cop", 5)
    survival_thief = scoring.get("survival_thief", 10)
    tie_score = scoring.get("tie_score", 2)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    series_id = f"series_{ts}_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(UTC).isoformat()
    logger.info(f"[run_series] Starting series {series_id} ({n_gamelets} gamelets)")

    gamelets: list[dict] = []
    cop_total = 0
    thief_total = 0
    runtime = PeerRuntime(
        role="cop",
        secret=secret,
        config_sha256=config_sha256,
        opponent_url=thief_url,
        games_dir=games_dir,
        group_name=group_name,
        llm_dict=llm_dict,
        my_endpoint=(orchestrator_config or {}).get("my_endpoint", ""),
        counted_mode=mode == RuntimeMode.COUNTED,
        orchestrator_config=orchestrator_config,
    )

    runtime.reset_for_new_series()

    for idx in range(1, n_gamelets + 1):
        gamelet_label = f"g{idx:02d}"
        game_id = f"{series_id}_{gamelet_label}"
        logger.info(f"[run_series] Gamelet {gamelet_label}: {game_id}")

        try:
            result = await runtime.run_game(game_id=game_id)
            winner = result.get("winner", "unknown")
            audit_ok = result.get("audit_ok", False)

            if winner == "TECHNICAL_LOSS" or not audit_ok:
                cop_pts = thief_pts = 0
            elif "cop_score" in result and "thief_score" in result:
                cop_pts = int(result["cop_score"])
                thief_pts = int(result["thief_score"])
            elif winner == "cop":
                cop_pts, thief_pts = capture_cop, capture_thief
            elif winner == "thief":
                cop_pts, thief_pts = survival_cop, survival_thief
            else:
                cop_pts = thief_pts = tie_score

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
                "token_totals": _validated_token_totals(result.get("token_totals")),
            }
        except Exception as exc:
            if mode == RuntimeMode.COUNTED:
                raise
            logger.error(f"[run_series] Gamelet {gamelet_label} failed: {exc}", exc_info=True)
            gamelet_record = {
                "gamelet": gamelet_label,
                "game_id": game_id,
                "winner": "error",
                "audit_ok": False,
                "cop_pts": 0,
                "thief_pts": 0,
                "error": str(exc),
                "token_totals": _validated_token_totals(),
            }

        gamelets.append(gamelet_record)
        logger.info(
            f"[run_series] {gamelet_label}: winner={gamelet_record['winner']} "
            f"cop+={gamelet_record['cop_pts']} thief+={gamelet_record['thief_pts']}"
        )

    series_winner = (
        "cop" if cop_total > thief_total else "thief" if thief_total > cop_total else "tie"
    )
    return runtime, gamelets, series_id, started_at, cop_total, thief_total, series_winner
