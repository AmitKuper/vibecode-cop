#!/usr/bin/env python3
"""Run a six-gamelet P2P series via PeerRuntime (cop drives, thief responds).

The cop PeerRuntime drives each gamelet by calling the thief's MCP directly —
no central coordinator is involved.

Prerequisites:
  1. Start the thief agent:  python -m thief thief/config.toml
  2. Run this script from the cop repo root:

     python scripts/run_series.py --thief-url http://localhost:5001/mcp

Optional arguments:
  --thief-url     Thief's MCP endpoint  (default: http://localhost:5001/mcp)
  --secret        Shared HMAC secret    (default: dev-secret-change-me)
  --games-dir     Directory for output  (default: cop/games)
  --n-gamelets    Number of gamelets    (default: 6)
  --config        Path to config.toml   (default: cop/config.toml or config.toml)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a P2P series via cop PeerRuntime.")
    p.add_argument("--thief-url", default=os.getenv("THIEF_URL", "http://localhost:5001/mcp"))
    p.add_argument("--secret", default=os.getenv("SHARED_SECRET", ""))
    p.add_argument("--games-dir", default="cop/games")
    p.add_argument("--n-gamelets", type=int, default=6,
                   help="Number of gamelets (must be >= 6 per league rules; default: 6)")
    p.add_argument("--config", default="")
    return p.parse_args()


def _load_config(args: argparse.Namespace) -> dict:
    """Load config.toml for secret and games_dir if not set via CLI."""
    config_path_candidates = [args.config] if args.config else [
        "cop/config.toml", "config.toml",
    ]
    for path_str in config_path_candidates:
        path = Path(path_str)
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    return {}


async def run_series(
    thief_url: str,
    secret: str,
    config_sha256: str,
    games_dir: Path,
    n_gamelets: int,
    group_name: str,
    llm_dict: dict | None = None,
) -> dict:
    """Run n_gamelets via cop PeerRuntime (P2P, no central judge)."""
    from agent.peer_runtime import PeerRuntime
    from agent.config.shared_config import load_shared_config

    shared_cfg = load_shared_config()
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

    for idx in range(1, n_gamelets + 1):
        gamelet_label = f"g{idx:02d}"
        game_id = f"{series_id}_{gamelet_label}"
        logger.info(f"[run_series] Gamelet {gamelet_label}: {game_id}")

        try:
            # Each gamelet gets a fresh PeerRuntime so board state is reset
            runtime = PeerRuntime(
                role="cop",
                secret=secret,
                config_sha256=config_sha256,
                opponent_url=thief_url,
                games_dir=games_dir,
                group_name=group_name,
                llm_dict=llm_dict,
            )
            result = await runtime.run_game(game_id=game_id)
            winner = result.get("winner", "unknown")
            audit_ok = result.get("audit_ok", False)

            if winner == "TECHNICAL_LOSS" or not audit_ok:
                cop_pts = thief_pts = 0
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
            }
        except Exception as exc:
            logger.error(f"[run_series] Gamelet {gamelet_label} failed: {exc}", exc_info=True)
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
            f"[run_series] {gamelet_label}: winner={gamelet_record['winner']} "
            f"cop+={gamelet_record['cop_pts']} thief+={gamelet_record['thief_pts']}"
        )

    series_winner = (
        "cop" if cop_total > thief_total
        else "thief" if thief_total > cop_total
        else "tie"
    )
    series_result = {
        "series_id": series_id,
        "config_sha256": config_sha256,
        "n_gamelets": n_gamelets,
        "gamelets": gamelets,
        "cop_total": cop_total,
        "thief_total": thief_total,
        "series_winner": series_winner,
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
    }

    out_path = games_dir / f"result_{series_id}_series.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(series_result, indent=2), encoding="utf-8")
    logger.info(
        f"[run_series] Done: {series_winner} wins (cop {cop_total} – thief {thief_total}). "
        f"Result: {out_path}"
    )
    return series_result


async def main() -> int:
    args = _parse_args()
    config = _load_config(args)

    secret = args.secret or os.environ.get("SHARED_SECRET") or (
        config.get("crypto", {}).get("shared_secret", "dev-secret-change-me")
    )
    games_dir = Path(args.games_dir)
    thief_url = args.thief_url
    if not thief_url.endswith("/mcp"):
        thief_url = thief_url.rstrip("/") + "/mcp"

    from agent.config.shared_config import load_shared_config, config_sha256 as _sha256_fn
    game_cfg = load_shared_config()
    config_sha256 = _sha256_fn(game_cfg)
    group_name = game_cfg.get("network_and_league", {}).get("group_name", "unknown")

    llm_dict = config.get("llm") or None

    n_gamelets = max(args.n_gamelets, 6)  # league minimum is 6
    if n_gamelets != args.n_gamelets:
        logger.warning(f"[run_series] --n-gamelets {args.n_gamelets} is below minimum 6; using 6")
    result = await run_series(
        thief_url=thief_url,
        secret=secret,
        config_sha256=config_sha256,
        games_dir=games_dir,
        n_gamelets=n_gamelets,
        group_name=group_name,
        llm_dict=llm_dict,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
