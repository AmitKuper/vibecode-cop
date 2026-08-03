"""Pure deterministic domain transition function.

apply_joint_action() is the single source of truth for all game physics:
- bounds and barriers
- orthogonal movement and STAY
- barrier quota and PLACE_* actions
- barrier-on-thief capture
- position-overlap capture
- trapped-thief detection (STAY excluded)
- turn increment
- survival threshold
- outcome determination

This function is pure: it takes immutable state and returns a new state.
No side effects. Both cop and thief repos must produce identical results
for the same inputs (verified by cross-repo conformance tests).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass

from agent.domain.config_validator import GameConfig
from agent.domain.types import DomainState, MoveRecord
from agent.rules_outcomes import GameOutcome

logger = logging.getLogger(__name__)

# Orthogonal deltas (STAY excluded — STAY(0,0) does not change position)
_MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "EAST": (1, 0),
    "WEST": (-1, 0),
    "STAY": (0, 0),
}

# Short-form aliases accepted from peer messages
_ALIASES: dict[str, str] = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}

# PLACE_* actions for cop barrier placement
_PLACE_DELTAS: dict[str, tuple[int, int]] = {
    "PLACE_N": (0, -1),
    "PLACE_S": (0, 1),
    "PLACE_E": (1, 0),
    "PLACE_W": (-1, 0),
}


@dataclass(frozen=True)
class TransitionResult:
    """Immutable result of apply_joint_action()."""

    new_state: DomainState
    outcome: GameOutcome
    cop_action_legal: bool
    thief_action_legal: bool
    barrier_placed: bool
    barrier_position: tuple[int, int] | None
    capture: bool
    trapped: bool
    error: str | None


def _normalize(action: str) -> str:
    return _ALIASES.get(action.upper(), action.upper())


def _is_valid(x: int, y: int, g: int, barriers: list[tuple[int, int]]) -> bool:
    return 0 <= x < g and 0 <= y < g and (x, y) not in barriers


def _has_orthogonal_escape(pos: tuple[int, int], g: int, barriers: list[tuple[int, int]]) -> bool:
    x, y = pos
    for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
        if _is_valid(x + dx, y + dy, g, barriers):
            return True
    return False


def apply_joint_action(
    state: DomainState,
    cop_action: str,
    thief_action: str,
    config: GameConfig | None = None,
) -> TransitionResult:
    """Apply one joint action to the domain state and return the transition result.

    This is the canonical implementation of game physics for both repositories.
    Identical inputs must produce identical outputs on both peers.

    Args:
        state: Current authoritative game state.
        cop_action: Cop's action — movement (N/S/E/W/STAY) or barrier (PLACE_N/S/E/W).
        thief_action: Thief's action — movement only (N/S/E/W/STAY).
        config: Optional game configuration; uses Appendix-F defaults if None.

    Returns:
        TransitionResult with new state and outcome.
    """
    max_turns = config.max_moves if config else 35
    g = state.grid_size

    barrier_set = list(state.barriers)
    barriers_as_tuples = [tuple(b) for b in barrier_set]
    cop_pos = state.cop_position
    thief_pos = state.thief_position
    cop_barriers_remaining = state.cop_barriers_remaining
    turn = state.turn

    cop_norm = _normalize(cop_action)
    thief_norm = _normalize(thief_action)

    barrier_placed = False
    barrier_position: tuple[int, int] | None = None
    cop_action_legal = True
    thief_action_legal = True
    error: str | None = None

    # --- 1. Barrier placement (cop only) ---
    effective_cop_move = cop_norm
    if cop_norm in _PLACE_DELTAS:
        effective_cop_move = "STAY"
        if cop_barriers_remaining <= 0:
            cop_action_legal = False
            error = "cop has no barriers remaining"
        else:
            dx, dy = _PLACE_DELTAS[cop_norm]
            bx, by = cop_pos[0] + dx, cop_pos[1] + dy
            if not (0 <= bx < g and 0 <= by < g):
                cop_action_legal = False
                error = f"barrier target ({bx},{by}) is out of bounds"
            elif (bx, by) in barriers_as_tuples:
                cop_action_legal = False
                error = f"barrier already at ({bx},{by})"
            else:
                barrier_position = (bx, by)
                barriers_as_tuples.append(barrier_position)
                barrier_set.append(list(barrier_position))
                cop_barriers_remaining -= 1
                barrier_placed = True

    # --- 2. Check barrier-on-thief capture (before movement) ---
    if barrier_placed and barrier_position == thief_pos:
        # Barrier placed on thief's cell: cop capture, game ends immediately
        new_history = list(state.move_history) + [
            MoveRecord(
                turn=turn,
                cop_move=cop_action,
                thief_move=thief_action,
                cop_position=cop_pos,
                thief_position=thief_pos,
            )
        ]
        new_state = DomainState(
            turn=turn + 1,
            grid_size=g,
            cop_position=cop_pos,
            thief_position=thief_pos,
            barriers=barrier_set,
            cop_barriers_remaining=cop_barriers_remaining,
            move_history=new_history,
            scent_grid=copy.deepcopy(state.scent_grid),
        )
        return TransitionResult(
            new_state=new_state,
            outcome=GameOutcome.COP_WIN,
            cop_action_legal=True,
            thief_action_legal=True,
            barrier_placed=True,
            barrier_position=barrier_position,
            capture=True,
            trapped=False,
            error=None,
        )

    # --- 3. Apply cop movement ---
    if effective_cop_move not in _MOVE_DELTAS:
        cop_action_legal = False
        effective_cop_move = "STAY"
        error = f"unknown cop move {cop_action!r}"

    cdx, cdy = _MOVE_DELTAS[effective_cop_move]
    ncx, ncy = cop_pos[0] + cdx, cop_pos[1] + cdy
    if effective_cop_move != "STAY" and not _is_valid(ncx, ncy, g, barriers_as_tuples):
        cop_action_legal = False
        ncx, ncy = cop_pos
    elif effective_cop_move == "STAY":
        ncx, ncy = cop_pos
    new_cop_pos = (ncx, ncy)

    # --- 4. Apply thief movement ---
    if thief_norm not in _MOVE_DELTAS:
        thief_action_legal = False
        thief_norm = "STAY"

    tdx, tdy = _MOVE_DELTAS[thief_norm]
    ntx, nty = thief_pos[0] + tdx, thief_pos[1] + tdy
    if thief_norm != "STAY" and not _is_valid(ntx, nty, g, barriers_as_tuples):
        thief_action_legal = False
        ntx, nty = thief_pos
    elif thief_norm == "STAY":
        ntx, nty = thief_pos
    new_thief_pos = (ntx, nty)

    # --- 5. Record history and increment turn ---
    new_history = list(state.move_history) + [
        MoveRecord(
            turn=turn,
            cop_move=cop_action,
            thief_move=thief_action,
            cop_position=new_cop_pos,
            thief_position=new_thief_pos,
        )
    ]
    new_turn = turn + 1

    # --- 6. Check position-overlap capture ---
    capture = new_cop_pos == new_thief_pos or new_thief_pos in [tuple(b) for b in barrier_set]
    if capture:
        new_state = DomainState(
            turn=new_turn,
            grid_size=g,
            cop_position=new_cop_pos,
            thief_position=new_thief_pos,
            barriers=barrier_set,
            cop_barriers_remaining=cop_barriers_remaining,
            move_history=new_history,
            scent_grid=_update_scent(state.scent_grid, new_thief_pos, g),
        )
        return TransitionResult(
            new_state=new_state,
            outcome=GameOutcome.COP_WIN,
            cop_action_legal=cop_action_legal,
            thief_action_legal=thief_action_legal,
            barrier_placed=barrier_placed,
            barrier_position=barrier_position,
            capture=True,
            trapped=False,
            error=error,
        )

    # --- 7. Check survival threshold ---
    if new_turn >= max_turns:
        new_state = DomainState(
            turn=new_turn,
            grid_size=g,
            cop_position=new_cop_pos,
            thief_position=new_thief_pos,
            barriers=barrier_set,
            cop_barriers_remaining=cop_barriers_remaining,
            move_history=new_history,
            scent_grid=_update_scent(state.scent_grid, new_thief_pos, g),
        )
        return TransitionResult(
            new_state=new_state,
            outcome=GameOutcome.THIEF_WIN,
            cop_action_legal=cop_action_legal,
            thief_action_legal=thief_action_legal,
            barrier_placed=barrier_placed,
            barrier_position=barrier_position,
            capture=False,
            trapped=False,
            error=error,
        )

    # --- 8. Check trapping (STAY excluded) ---
    trapped = not _has_orthogonal_escape(new_thief_pos, g, barriers_as_tuples)
    new_scent = _update_scent(state.scent_grid, new_thief_pos, g)
    new_state = DomainState(
        turn=new_turn,
        grid_size=g,
        cop_position=new_cop_pos,
        thief_position=new_thief_pos,
        barriers=barrier_set,
        cop_barriers_remaining=cop_barriers_remaining,
        move_history=new_history,
        scent_grid=new_scent,
    )

    outcome = GameOutcome.COP_WIN if trapped else GameOutcome.ONGOING

    return TransitionResult(
        new_state=new_state,
        outcome=outcome,
        cop_action_legal=cop_action_legal,
        thief_action_legal=thief_action_legal,
        barrier_placed=barrier_placed,
        barrier_position=barrier_position,
        capture=False,
        trapped=trapped,
        error=error,
    )


# Mandatory scent emission kernel (Appendix-F, 5×5 radial).
# Keyed by squared Euclidean distance from emitter.
_SCENT_KERNEL: dict[int, float] = {0: 0.90, 1: 0.62, 2: 0.42, 4: 0.20, 5: 0.14, 8: 0.04}
_SCENT_DECAY = 0.9


def _update_scent(
    prev: list[list[float]],
    thief_pos: tuple[int, int],
    g: int,
) -> list[list[float]]:
    """Decay and re-emit scent according to the Appendix-F specification."""
    tx, ty = thief_pos
    grid = [[0.0] * g for _ in range(g)] if not prev else [row[:] for row in prev]
    for y in range(g):
        for x in range(g):
            dist_sq = (x - tx) ** 2 + (y - ty) ** 2
            emission = _SCENT_KERNEL.get(dist_sq, 0.0)
            grid[y][x] = round(_SCENT_DECAY * grid[y][x] + emission, 4)
    return grid
