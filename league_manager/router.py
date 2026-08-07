"""ProtocolDialectRouter — routes inbound ref-v3 calls to the correct worker."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Role schedule: sub_game_number → which worker is active
# COP plays sub-games 1, 3, 5; THIEF plays sub-games 2, 4, 6 (default)
DEFAULT_ROLE_SCHEDULE: dict[int, str] = {
    1: "cop",
    2: "thief",
    3: "cop",
    4: "thief",
    5: "cop",
    6: "thief",
}


class RouterError(Exception):
    """Raised when routing fails."""


class Router:
    """Routes inbound ref-v3 MCP tool calls to the correct worker.

    LM validates routing identity only — it does not validate game state,
    step numbers, or commit-reveal sequencing. Workers do that.
    """

    def __init__(
        self, cop_worker, thief_worker, role_schedule: dict[int, str] | None = None
    ) -> None:
        """Initialise router with worker references and role schedule.

        Args:
            cop_worker: Cop worker instance (real or mock).
            thief_worker: Thief worker instance (real or mock).
            role_schedule: Dict mapping sub_game_number → 'cop'|'thief'. Uses default if None.
        """
        self._cop = cop_worker
        self._thief = thief_worker
        self._schedule = role_schedule or dict(DEFAULT_ROLE_SCHEDULE)
        self._series: dict[str, dict] = {}  # game_uid → series metadata

    def register_series(self, game_uid: str, starting_role: str = "police") -> None:
        """Register a new series so it can be routed.

        Args:
            game_uid: Canonical series identity.
            starting_role: Which role plays sub-game 1 ('police' or 'thief').
        """
        if starting_role == "thief":
            schedule = {k: ("thief" if v == "cop" else "cop") for k, v in self._schedule.items()}
        else:
            schedule = dict(self._schedule)
        self._series[game_uid] = {"schedule": schedule}
        logger.info("Registered series %s starting=%s", game_uid[:8], starting_role)

    def get_role_for_sub_game(self, game_uid: str, sub_game_number: int) -> str:
        """Return the role ('cop' or 'thief') that plays the given sub-game.

        Args:
            game_uid: Series identity.
            sub_game_number: Sub-game index 1..6.

        Returns:
            'cop' or 'thief'.

        Raises:
            RouterError: If game_uid is unknown.
        """
        if game_uid not in self._series:
            raise RouterError(f"unknown game_uid: {game_uid!r}")
        return self._series[game_uid]["schedule"].get(sub_game_number, "cop")

    def route(self, game_uid: str, sub_game_number: int, tool: str, payload: dict) -> dict:
        """Route a tool call to the correct worker.

        Args:
            game_uid: Series identity.
            sub_game_number: Sub-game index 1..6.
            tool: MCP tool name to call on the worker.
            payload: Payload dict for the tool.

        Returns:
            Worker response dict.

        Raises:
            RouterError: If game_uid unknown, sub_game_number out of range, or worker call fails.
        """
        if game_uid not in self._series:
            raise RouterError(f"unknown game_uid: {game_uid!r}")
        if sub_game_number not in range(1, 7):
            raise RouterError(f"sub_game_number must be 1..6, got {sub_game_number}")
        schedule = self._series[game_uid]["schedule"]
        worker_role = schedule[sub_game_number]
        worker = self._cop if worker_role == "cop" else self._thief
        logger.debug(
            "Route %s sg%d → %s worker tool=%s", game_uid[:8], sub_game_number, worker_role, tool
        )
        fn = getattr(worker, tool, None)
        if fn is None:
            raise RouterError(f"Worker has no tool: {tool!r}")
        if payload:
            return fn(game_uid, sub_game_number, **payload)
        return fn(game_uid, sub_game_number)
