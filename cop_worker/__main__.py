"""Entry point for cop_worker subprocess — starts internal MCP server."""

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
    """Parse CLI args and start the cop_worker MCP server.

    Commands:
      serve   Start the MCP server (default, counted mode supported).
    """
    parser = argparse.ArgumentParser(
        description=(
            "cop_worker: counted-mode MCP server for the cop agent. "
            "Use 'serve' to start the counted game server."
        )
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand")
    serve_parser = subparsers.add_parser(
        "serve",
        help="Serve the cop MCP endpoint (counted mode enforced in production).",
    )
    serve_parser.add_argument("--port", type=int, default=61224, help="MCP server port")
    serve_parser.add_argument("--config", default="cop_config.yaml", help="Config YAML path")
    serve_parser.add_argument("--log-dir", default="logs", help="Log output directory")
    serve_parser.add_argument("--report-dir", default="reports", help="Report output directory")
    serve_parser.add_argument(
        "--counted",
        action="store_true",
        default=False,
        help="Enable counted (production) mode — enforces all COUNTED constraints.",
    )
    # Top-level flags for direct invocation (no subcommand)
    parser.add_argument("--port", type=int, default=61224, help="MCP server port")
    parser.add_argument("--config", default="cop_config.yaml", help="Config YAML path")
    parser.add_argument("--log-dir", default="logs", help="Log output directory")
    parser.add_argument("--report-dir", default="reports", help="Report output directory")
    parser.add_argument(
        "--counted",
        action="store_true",
        default=False,
        help="Enable counted (production) mode.",
    )
    args = parser.parse_args()
    # If subcommand 'serve' was used, its namespace is in args directly
    setup_logging(log_dir=args.log_dir)
    logger = logging.getLogger(__name__)
    logger.info("cop_worker starting port=%d config=%s", args.port, args.config)

    from mcp.server.fastmcp import FastMCP

    from cop_worker import mcp_server

    app = FastMCP(
        "cop_worker",
        host="0.0.0.0",
        port=args.port,
    )

    @app.tool()
    def start_gamelet(
        game_uid: str,
        sub_game_number: int,
        terms: dict,
        opponent_group: str,
        role: str,
    ) -> dict:
        """Start a new gamelet."""
        return mcp_server.start_gamelet(game_uid, sub_game_number, terms, opponent_group, role)

    @app.tool()
    def start_playing(game_uid: str, sub_game_number: int) -> dict:
        """Transition gamelet to PLAYING state."""
        return mcp_server.start_playing(game_uid, sub_game_number)

    @app.tool()
    def deliver_event(
        game_uid: str,
        sub_game_number: int,
        event_type: str,
        payload: dict,
    ) -> dict:
        """Deliver an event to a gamelet."""
        return mcp_server.deliver_event(game_uid, sub_game_number, event_type, payload)

    @app.tool()
    def get_status(game_uid: str, sub_game_number: int) -> dict:
        """Get gamelet status."""
        return mcp_server.get_status(game_uid, sub_game_number)

    @app.tool()
    def prepare_audit(game_uid: str, sub_game_number: int) -> dict:
        """Prepare audit bundle."""
        return mcp_server.prepare_audit(game_uid, sub_game_number)

    @app.tool()
    def get_result(game_uid: str, sub_game_number: int) -> dict:
        """Get gamelet result."""
        return mcp_server.get_result(game_uid, sub_game_number)

    @app.tool()
    def shutdown_gamelet(game_uid: str, sub_game_number: int) -> dict:
        """Shutdown a gamelet."""
        return mcp_server.shutdown_gamelet(game_uid, sub_game_number)

    logger.info("cop_worker MCP server ready on port %d (streamable-http)", args.port)
    app.run(transport="streamable-http")


if __name__ == "__main__":
    main()
