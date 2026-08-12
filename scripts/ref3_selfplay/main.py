"""Main entry: probe transport, drive the series, emit structured results."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging

from ref3_selfplay.runtime import LOG_DIR, THIEF_REPO, logger
from ref3_selfplay.series import _run_subgames
from ref3_selfplay.transport import _try_real_http_probe

_DESCRIPTION = """Run a real ref-v3 self-play game over HTTP MCP transport (in-process variant).

Side A (cop_worker) plays as "police".
Side B (thief_worker) plays as "thief".
They exchange moves formatted strictly in ref-v3 wire format.

Real HTTP transport (FastMCP streamable-http) is probed first; if the endpoint
is unreachable, the game loop falls back to direct in-process calls with the
same ref-v3 message format, proving the protocol logic.

Usage:
    uv run python scripts/run_ref3_selfplay.py --sub-games 6 --max-steps 5
"""


def main() -> int:
    """Run ref-v3 self-play series and emit structured results."""
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument("--sub-games", type=int, default=6, help="Number of sub-games (default 6)")
    parser.add_argument("--max-steps", type=int, default=5, help="Steps per sub-game (default 5)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # --- Probe HTTP transport availability ---
    http_probe = _try_real_http_probe()
    print("\nHTTP transport probe:")
    print(f"  cop_worker  {http_probe['cop_url']}  reachable={http_probe['cop_reachable']}")
    print(f"  thief_worker {http_probe['thief_url']}  reachable={http_probe['thief_reachable']}")
    transport_mode = (
        "real-http"
        if http_probe["cop_reachable"] and http_probe["thief_reachable"]
        else "in-process"
    )
    print(f"  transport_mode: {transport_mode}\n")

    # --- Import worker modules ---
    import cop_worker.mcp_server as cop_ms  # noqa: PLC0415

    try:
        import thief_worker.mcp_server as thief_ms  # noqa: PLC0415
    except ImportError as exc:
        logger.error("thief_worker not importable: %s", exc)
        logger.error("Ensure vibecode-thief is at %s", THIEF_REPO)
        return 1

    # --- Import league infrastructure ---
    from league_manager.series_jsonl import SeriesJSONL  # noqa: PLC0415
    from league_manager.series_lifecycle import SeriesLifecycle  # noqa: PLC0415

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = LOG_DIR / "league_ref3.jsonl"

    game_uid = hashlib.sha256(b"ref3_selfplay_001").hexdigest()[:32]
    game_id = "ref3_001"

    sl = SeriesLifecycle(game_uid=game_uid, game_id=game_id)
    jsonl = SeriesJSONL(jsonl_path)

    # Reset in-process registries for a clean run (no-op when using real HTTP)
    if transport_mode == "in-process":
        cop_ms.clear_all_gamelets()
        thief_ms.clear_all_gamelets()

    print(f"ref-v3 self-play series  game_uid={game_uid}")
    print(f"sub-games={args.sub_games}  max-steps={args.max_steps}  transport={transport_mode}\n")

    jsonl.append(
        "series_created",
        game_uid=game_uid,
        game_id=game_id,
        protocol="reference-v3",
        transport=transport_mode,
    )

    cop_wins, thief_wins = _run_subgames(
        args,
        game_uid,
        game_id,
        cop_ms,
        thief_ms,
        http_probe,
        transport_mode,
        sl,
        jsonl,
    )

    jsonl.append(
        "series_settled",
        game_uid=game_uid,
        game_id=game_id,
        cop_wins=cop_wins,
        thief_wins=thief_wins,
        series_closed=sl.is_closed,
        protocol="reference-v3",
        transport=transport_mode,
    )

    result = {
        "status": "COMPLETE",
        "game_uid": game_uid,
        "game_id": game_id,
        "protocol": "reference-v3",
        "transport": transport_mode,
        "cop_wins": cop_wins,
        "thief_wins": thief_wins,
        "series_closed": sl.is_closed,
        "http_probe": http_probe,
        "jsonl_path": str(jsonl_path),
    }

    print("=== Series result ===")
    print(json.dumps(result, indent=2))

    print("\n=== JSONL log ===")
    for rec in jsonl.read_all():
        print(json.dumps(rec))

    return 0
