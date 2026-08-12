"""Shared observation factories for the hidden-coordinate-leak test modules."""

from __future__ import annotations

from cop_worker.observation import LocalObservation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_scent(n: int = 7) -> list[list[float]]:
    return [[0.0] * n for _ in range(n)]


def _make_obs(role: str, own_pos: tuple, grid_size: int = 7) -> LocalObservation:
    return LocalObservation(
        own_position=own_pos,
        own_barriers_remaining=14 if role == "cop" else 0,
        known_barriers=[],
        opponent_scent=_empty_scent(grid_size),
        last_hint="",
        step=1,
        gamelet=1,
        grid_size=grid_size,
    )
