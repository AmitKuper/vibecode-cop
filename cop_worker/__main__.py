"""Entry point for cop_worker subprocess."""

from __future__ import annotations

import argparse
import logging

from cop_worker.logging_setup import setup_dual_logging


def setup_logging(log_dir: str = "logs") -> None:
    """Configure logging for the cop_worker process.

    Delegates to setup_dual_logging with a cop_worker prefix.

    Args:
        log_dir: Directory to write log files.
    """
    setup_dual_logging(prefix="cop_worker", log_dir=log_dir)


def main() -> None:
    """Parse CLI args and start the cop_worker MCP server."""
    parser = argparse.ArgumentParser(description="cop_worker MCP server")
    parser.add_argument("--port", type=int, default=8001, help="MCP server port")
    parser.add_argument("--config", default="cop_config.yaml", help="Config YAML path")
    parser.add_argument("--log-dir", default="logs", help="Log output directory")
    parser.add_argument("--report-dir", default="reports", help="Report output directory")
    args = parser.parse_args()
    setup_logging(log_dir=args.log_dir)
    logger = logging.getLogger(__name__)
    logger.info("cop_worker starting port=%d config=%s", args.port, args.config)
    # MCP server wiring will be added in Phase 3/4 when FastMCP or equivalent is chosen.
    # For now, log startup and keep process alive for integration testing.
    logger.info("cop_worker ready (stub — MCP transport pending)")


if __name__ == "__main__":
    main()
