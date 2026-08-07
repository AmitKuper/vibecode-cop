"""Entry point for league_manager."""

from __future__ import annotations

import argparse
import logging

from cop_worker.logging_setup import setup_dual_logging


def main() -> None:
    """Parse CLI args and start the LeagueManager."""
    parser = argparse.ArgumentParser(description="LeagueManager MCP server")
    parser.add_argument("--config", default="league_manager.yaml", help="Config YAML path")
    parser.add_argument("--port", type=int, default=8000, help="External MCP port")
    parser.add_argument("--admin-port", type=int, default=8080, help="Admin HTTP port")
    parser.add_argument("--counted", action="store_true", help="Enable counted match mode")
    parser.add_argument("--log-dir", default="logs", help="Log output directory")
    args = parser.parse_args()
    setup_dual_logging(prefix="league_manager", log_dir=args.log_dir)
    logger = logging.getLogger(__name__)
    logger.info(
        "league_manager starting port=%d admin=%d counted=%s",
        args.port,
        args.admin_port,
        args.counted,
    )
    logger.info("league_manager ready (stub — MCP transport pending)")


if __name__ == "__main__":
    main()
