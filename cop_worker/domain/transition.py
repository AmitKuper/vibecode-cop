"""Pure deterministic domain transition function.

apply_joint_action() is the single source of truth for all game physics:
bounds/barriers, orthogonal movement and STAY, barrier quota and PLACE_*
actions, barrier-on-thief capture, position-overlap capture, trapped-thief
detection (STAY excluded), turn increment, survival threshold, and outcome
determination. It is pure: immutable state in, new state out; both repos
must produce identical results for the same inputs (verified by cross-repo
conformance tests). Result construction lives in transition_result.py.
"""

from __future__ import annotations

from cop_worker.domain.config_validator import GameConfig
from cop_worker.domain.transition_geometry import (
    _MOVE_DELTAS,
    _PLACE_DELTAS,
    _has_orthogonal_escape,
    _is_valid,
    _normalize,
)
from cop_worker.domain.transition_result import (  # noqa: F401  (re-export)
    TransitionResult,
    _finish,
)
from cop_worker.domain.types import DomainState, MoveRecord
from cop_worker.rules_outcomes import GameOutcome


def apply_joint_action(
    state: DomainState,
    cop_action: str,
    thief_action: str,
    config: GameConfig | None = None,
) -> TransitionResult:
    """Apply one joint action (cop: N/S/E/W/STAY or PLACE_*; thief: movement
    only) to the domain state and return the TransitionResult. Canonical game
    physics for both repositories: identical inputs must produce identical
    outputs on both peers. ``config`` defaults to Appendix-F values."""
    cfg = config or GameConfig()
    g = state.grid_size
    barrier_set = list(state.barriers)
    barriers_as_tuples = [tuple(b) for b in barrier_set]
    preexisting_barriers = list(barriers_as_tuples)
    cop_pos, thief_pos = state.cop_position, state.thief_position
    cop_barriers_remaining, turn = state.cop_barriers_remaining, state.turn
    cop_norm, thief_norm = _normalize(cop_action), _normalize(thief_action)
    barrier_placed, barrier_position = False, None
    cop_action_legal = thief_action_legal = True
    error: str | None = None

    # --- 1. Barrier placement (cop only) ---
    effective_cop_move = cop_norm
    if cop_norm in _PLACE_DELTAS:
        effective_cop_move = "STAY"
        if cop_barriers_remaining <= 0:
            cop_action_legal, error = False, "cop has no barriers remaining"
        else:
            dx, dy = _PLACE_DELTAS[cop_norm]
            bx, by = cop_pos[0] + dx, cop_pos[1] + dy
            if not (0 <= bx < g and 0 <= by < g):
                cop_action_legal, error = False, f"barrier target ({bx},{by}) is out of bounds"
            elif (bx, by) in barriers_as_tuples:
                cop_action_legal, error = False, f"barrier already at ({bx},{by})"
            else:
                barrier_position = (bx, by)
                barriers_as_tuples.append(barrier_position)
                barrier_set.append(list(barrier_position))
                cop_barriers_remaining -= 1
                barrier_placed = True

    def _record(cop_at, thief_at) -> list:
        return list(state.move_history) + [
            MoveRecord(
                turn=turn,
                cop_move=cop_action,
                thief_move=thief_action,
                cop_position=cop_at,
                thief_position=thief_at,
            )
        ]

    # --- 2. Check barrier-on-thief capture (before movement) ---
    if barrier_placed and barrier_position == thief_pos:
        # Barrier placed on thief's cell: cop capture, game ends immediately
        return _finish(
            state, turn=turn + 1, cop_position=cop_pos, thief_position=thief_pos,
            barriers=barrier_set, cop_barriers_remaining=cop_barriers_remaining,
            move_history=_record(cop_pos, thief_pos), outcome=GameOutcome.COP_WIN,
            cop_action_legal=True, thief_action_legal=True, barrier_placed=True,
            barrier_position=barrier_position, capture=True, trapped=False,
            cop_score=cfg.scoring.capture_cop, thief_score=cfg.scoring.capture_thief,
            error=None,
        )  # fmt: skip

    # --- 3. Apply cop movement ---
    if effective_cop_move not in _MOVE_DELTAS:
        cop_action_legal, effective_cop_move = False, "STAY"
        error = f"unknown cop move {cop_action!r}"
    cdx, cdy = _MOVE_DELTAS[effective_cop_move]
    ncx, ncy = cop_pos[0] + cdx, cop_pos[1] + cdy
    if effective_cop_move != "STAY" and not _is_valid(ncx, ncy, g, barriers_as_tuples):
        cop_action_legal = False
        ncx, ncy = cop_pos
    new_cop_pos = (ncx, ncy)  # STAY's zero delta already keeps cop_pos

    # --- 4. Apply thief movement ---
    if thief_norm not in _MOVE_DELTAS:
        thief_action_legal, thief_norm = False, "STAY"
    tdx, tdy = _MOVE_DELTAS[thief_norm]
    ntx, nty = thief_pos[0] + tdx, thief_pos[1] + tdy
    if thief_norm != "STAY" and not _is_valid(ntx, nty, g, preexisting_barriers):
        thief_action_legal = False
        ntx, nty = thief_pos
    elif thief_norm != "STAY" and barrier_position == (ntx, nty):
        # Both actions were legal when committed. A simultaneously placed
        # barrier blocks the destination deterministically; it does not turn
        # the thief's already-committed move into a protocol violation.
        ntx, nty = thief_pos
    new_thief_pos = (ntx, nty)  # STAY's zero delta already keeps thief_pos

    # --- 5-8. History, capture, survival threshold, trapping (STAY excluded) ---
    new_history = _record(new_cop_pos, new_thief_pos)
    new_turn = turn + 1
    capture = new_cop_pos == new_thief_pos or new_thief_pos in [tuple(b) for b in barrier_set]
    survived = not capture and new_turn >= cfg.survival_threshold
    trapped = (
        not capture
        and not survived
        and not _has_orthogonal_escape(new_thief_pos, g, barriers_as_tuples)
    )
    if capture or trapped:
        outcome = GameOutcome.COP_WIN
        cop_score, thief_score = cfg.scoring.capture_cop, cfg.scoring.capture_thief
    elif survived:
        outcome = GameOutcome.THIEF_WIN
        cop_score, thief_score = cfg.scoring.survival_cop, cfg.scoring.survival_thief
    else:
        outcome, cop_score, thief_score = GameOutcome.ONGOING, 0, 0
    return _finish(
        state, turn=new_turn, cop_position=new_cop_pos, thief_position=new_thief_pos,
        barriers=barrier_set, cop_barriers_remaining=cop_barriers_remaining,
        move_history=new_history, outcome=outcome,
        cop_action_legal=cop_action_legal, thief_action_legal=thief_action_legal,
        barrier_placed=barrier_placed, barrier_position=barrier_position,
        capture=capture, trapped=trapped,
        cop_score=cop_score, thief_score=thief_score, error=error,
    )  # fmt: skip
