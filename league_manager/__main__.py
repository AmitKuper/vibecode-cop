"""Entry point for league_manager — starts MCP server and admin API."""

from __future__ import annotations

import argparse
import logging
import threading

from cop_worker.logging_setup import setup_dual_logging


def _build_admin_app(admin_api):
    """Build a FastAPI ASGI app wrapping an AdminAPI instance.

    Args:
        admin_api: AdminAPI instance with start_league, get_status, restart_worker.

    Returns:
        FastAPI application.
    """
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    http_app = FastAPI(title="LeagueManager Admin API")

    class StartLeagueRequest(BaseModel):
        peer_url: str
        role: str
        league_id: str | None = None

    class RestartWorkerRequest(BaseModel):
        worker: str

    @http_app.post("/start-league")
    def start_league(req: StartLeagueRequest) -> dict:
        """Start a new league series."""
        try:
            return admin_api.start_league(req.peer_url, req.role, req.league_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @http_app.get("/status")
    def get_status() -> dict:
        """Return current system status."""
        return admin_api.get_status()

    @http_app.post("/restart-worker")
    def restart_worker(req: RestartWorkerRequest) -> dict:
        """Restart a named worker."""
        try:
            return admin_api.restart_worker(req.worker)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return http_app


def main() -> None:
    """Parse CLI args and start the LeagueManager."""
    parser = argparse.ArgumentParser(description="LeagueManager MCP server")
    parser.add_argument("--config", default="league_manager.yaml", help="Config YAML path")
    parser.add_argument("--port", type=int, default=8000, help="External MCP port")
    parser.add_argument(
        "--admin-port", type=int, default=8080, help="Admin HTTP port (localhost only)"
    )
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

    import uvicorn

    from league_manager.admin_api import AdminAPI
    from league_manager.worker_lifecycle import WorkerLifecycle

    worker_lifecycle = WorkerLifecycle()
    admin_api = AdminAPI(worker_lifecycle=worker_lifecycle)
    admin_app = _build_admin_app(admin_api)

    # Admin API on localhost only — daemon thread so it exits with main process
    admin_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": admin_app,
            "host": "127.0.0.1",
            "port": args.admin_port,
            "log_level": "warning",
        },
        daemon=True,
    )
    admin_thread.start()
    logger.info("Admin API started on http://127.0.0.1:%d", args.admin_port)

    from mcp.server.fastmcp import FastMCP

    from league_manager.mcp_server import LMMCPServer
    from league_manager.protocol.reference_v3_adapter import ReferenceV3Adapter
    from league_manager.router import Router

    adapter = ReferenceV3Adapter()
    router = Router(cop_worker=None, thief_worker=None)
    lm_server = LMMCPServer(router=router, adapter=adapter)

    app = FastMCP(
        "league_manager",
        host="0.0.0.0",
        port=args.port,
    )

    @app.tool()
    def negotiate(payload: dict) -> dict:
        """Handle negotiate tool call from peer."""
        return lm_server.negotiate(payload)

    @app.tool()
    def receive_turn(payload: dict) -> dict:
        """Handle receive_turn tool call from peer."""
        return lm_server.receive_turn(payload)

    @app.tool()
    def submit_audit(payload: dict) -> dict:
        """Handle submit_audit tool call from peer."""
        return lm_server.submit_audit(payload)

    @app.tool()
    def receive_control(payload: dict) -> dict:
        """Handle receive_control tool call from peer."""
        return lm_server.receive_control(payload)

    logger.info("LeagueManager MCP server ready on port %d (streamable-http)", args.port)
    app.run(transport="streamable-http")


if __name__ == "__main__":
    main()
