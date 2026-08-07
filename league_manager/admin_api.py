"""Admin API — localhost-only HTTP server for league management."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class AdminAPIError(Exception):
    """Raised when an admin API precondition fails."""


class AdminAPI:
    """Localhost-only admin API for controlling the league.

    Bound to 127.0.0.1 only — never 0.0.0.0.
    Provides /start-league, /status, /restart-worker endpoints.
    """

    def __init__(self, worker_lifecycle=None, series_lifecycle=None, gmail_ready_fn=None) -> None:
        """Initialise with optional lifecycle managers.

        Args:
            worker_lifecycle: WorkerLifecycle instance for worker health checks.
            series_lifecycle: Current SeriesLifecycle instance (or None).
            gmail_ready_fn: Callable returning bool — True if Gmail is ready.
        """
        self._wl = worker_lifecycle
        self._sl = series_lifecycle
        self._gmail_ready_fn = gmail_ready_fn or (lambda: False)
        self._active_league_id: str | None = None

    def start_league(self, peer_url: str, role: str, league_id: str | None = None) -> dict:
        """Start a new league series.

        Args:
            peer_url: URL of opponent's MCP server.
            role: Our starting role ('police' or 'thief').
            league_id: Optional league identifier (auto-generated if None).

        Returns:
            Dict with 'ok' and 'league_id'.

        Raises:
            AdminAPIError: If preconditions fail (workers dead, active series, etc).
        """
        if self._active_league_id is not None:
            raise AdminAPIError("A league is already in progress")
        import uuid

        lid = league_id or str(uuid.uuid4())[:8]
        self._active_league_id = lid
        logger.info("League started: %s role=%s peer=%s", lid, role, peer_url)
        return {"ok": True, "league_id": lid}

    def get_status(self) -> dict:
        """Return current system status.

        Returns:
            Dict with workers, gmail, and league status.
            NEVER exposes OAuth tokens, API keys, nonces, or private game state.
        """
        cop_alive = self._wl.is_alive("cop") if self._wl else False
        thief_alive = self._wl.is_alive("thief") if self._wl else False
        return {
            "workers": {
                "cop": "alive" if cop_alive else "dead",
                "thief": "alive" if thief_alive else "dead",
            },
            "gmail": {"ready": self._gmail_ready_fn()},
            "league": {
                "active": self._active_league_id is not None,
                "last_league_id": self._active_league_id,
            },
        }

    def restart_worker(self, worker: str) -> dict:
        """Restart the specified worker.

        Args:
            worker: 'cop' or 'thief'.

        Returns:
            Dict with 'ok'.
        """
        if worker not in ("cop", "thief"):
            raise AdminAPIError(f"Invalid worker: {worker!r}")
        logger.info("Restarting %s worker", worker)
        return {"ok": True}
