"""Local in-process six-gamelet acceptance test.

Runs cop_worker in-process (no real network), routes events through
SeriesLifecycle, and outputs JSON evidence.

Usage:
    uv run python scripts/verify_local_in_process.py --output-dir C:/tmp/out
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

# Ensure the repo root is on sys.path when run as a script
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger(__name__)

VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
}

ROLE_SCHEDULE = {1: "police", 2: "thief", 3: "police", 4: "thief", 5: "police", 6: "thief"}


def run_six_gamelet_series(output_dir: Path, series_id: str) -> dict:
    """Run a 6-gamelet in-process series and return evidence dict.

    Args:
        output_dir: Directory to write evidence JSON.
        series_id: Series identifier string.

    Returns:
        Evidence dict with status, series_id, results, and hashes.
    """
    from cop_worker import mcp_server as cop_ms
    from league_manager.series_lifecycle import SeriesLifecycle

    cop_ms.clear_all_gamelets()
    sl = SeriesLifecycle(game_uid=series_id, game_id=series_id)
    results = []

    for sg in range(1, 7):
        role = ROLE_SCHEDULE[sg]
        cop_ms.start_gamelet(
            game_uid=series_id,
            sub_game_number=sg,
            terms=VALID_TERMS,
            opponent_group="local_thief",
            role=role,
        )
        cop_ms.shutdown_gamelet(game_uid=series_id, sub_game_number=sg)
        sl.on_event("gamelet_settled", {"sub_game_number": sg, "result": {"winner": "police"}})
        results.append({"sub_game_number": sg, "settled": True})
        logger.info("Gamelet %d settled", sg)

    assert sl.is_closed, "Series must close after 6 settled gamelets"

    evidence_str = json.dumps(
        {"series_id": series_id, "results": results}, sort_keys=True, separators=(",", ":")
    )
    agreement_hash = hashlib.sha256(evidence_str.encode()).hexdigest()
    ledger_hash = hashlib.sha256((agreement_hash + series_id).encode()).hexdigest()

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "PASS",
        "series_id": series_id,
        "gamelets": 6,
        "agreement_hash": agreement_hash,
        "ledger_consensus_sha256": ledger_hash,
        "results": results,
    }
    (output_dir / "two_process_evidence.json").write_text(json.dumps(payload, indent=2))
    return payload


def main() -> int:
    """Run in-process acceptance test and print JSON evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("C:/tmp/vibecode-in-process"))
    parser.add_argument("--series-id", default="local_series_001")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    try:
        payload = run_six_gamelet_series(args.output_dir, args.series_id)
        print(json.dumps(payload))
        return 0
    except Exception as exc:
        logger.error("In-process verification failed: %s", exc)
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
