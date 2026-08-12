"""CLI argument parsing, config loading, and the async entry point."""

import argparse
import json
import logging
import os
import tomllib
from pathlib import Path

from series_run.core import run_series

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a P2P series via cop PeerRuntime.")
    p.add_argument("--thief-url", default=os.getenv("THIEF_URL", "http://localhost:5001/mcp"))
    p.add_argument("--secret", default=os.getenv("SHARED_SECRET", ""))
    p.add_argument("--games-dir", default="cop/games")
    p.add_argument(
        "--n-gamelets",
        type=int,
        default=6,
        help="Number of gamelets (must be >= 6 per league rules; default: 6)",
    )
    p.add_argument("--config", default="")
    p.add_argument(
        "--mode",
        choices=["counted", "warmup", "development"],
        default="development",
        help="Runtime mode (default: development)",
    )
    p.add_argument(
        "--counted",
        action="store_true",
        help="Deprecated alias for --mode counted",
    )
    return p.parse_args()


def _load_config(args: argparse.Namespace) -> dict:
    """Load config.toml for secret and games_dir if not set via CLI."""
    config_path_candidates = (
        [args.config]
        if args.config
        else [
            "cop/config.toml",
            "config.toml",
        ]
    )
    for path_str in config_path_candidates:
        path = Path(path_str)
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    return {}


async def main() -> int:
    from cop_worker.logging_setup import setup_dual_logging

    args = _parse_args()
    setup_dual_logging(prefix="run_series_cop")
    config = _load_config(args)

    secret = (
        args.secret
        or os.environ.get("SHARED_SECRET")
        or (config.get("crypto", {}).get("shared_secret", "dev-secret-change-me"))
    )
    games_dir = Path(args.games_dir)
    thief_url = args.thief_url
    if not thief_url.endswith("/mcp"):
        thief_url = thief_url.rstrip("/") + "/mcp"

    from cop_worker.config.shared_config import config_sha256 as _sha256_fn
    from cop_worker.config.shared_config import load_shared_config

    game_cfg = load_shared_config()
    config_sha256 = _sha256_fn(game_cfg)
    group_name = game_cfg.get("network_and_league", {}).get("group_name", "unknown")

    llm_dict = config.get("llm") or None

    from cop_worker.runtime_mode import RuntimeMode

    mode = RuntimeMode.COUNTED if args.counted else RuntimeMode(args.mode)

    # Build orchestrator config with Gmail sender if configured
    orchestrator_config: dict | None = None
    gmail_cfg = config.get("reports", {}).get("gmail", {})
    if gmail_cfg.get("mode") == "send" or gmail_cfg.get("token_path"):
        try:
            from league_manager.gmail.sender import GmailApiSender

            token_path = gmail_cfg.get("token_path", "secrets/gmail/token.json")
            orchestrator_config = {"gmail_sender": GmailApiSender(token_path)}
            logger.info("[run_series] Gmail sender loaded from %s", token_path)
        except Exception as exc:
            logger.warning("[run_series] Gmail sender not available: %s", exc)

    # Counted series must be exactly 6 gamelets (binding league rule).
    if args.n_gamelets != 6:
        logger.error(
            f"[run_series] --n-gamelets {args.n_gamelets} rejected. "
            "Counted series requires exactly 6 gamelets."
        )
        return 1
    n_gamelets = 6
    result = await run_series(
        thief_url=thief_url,
        secret=secret,
        config_sha256=config_sha256,
        games_dir=games_dir,
        n_gamelets=n_gamelets,
        group_name=group_name,
        llm_dict=llm_dict,
        mode=mode,
        orchestrator_config=orchestrator_config,
    )
    print(json.dumps(result, indent=2))
    return 0
