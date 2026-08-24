"""Transition result construction (split from transition.py, 150-line rule).

The four terminal paths of apply_joint_action() built byte-identical
DomainState/TransitionResult pairs inline; _finish() is that construction,
verbatim, in one place. Pure, no behavior change — pinned by the kit's
frozen vectors and the cross-repo conformance suites.
"""

from __future__ import annotations

from dataclasses import dataclass

from cop_worker.domain.transition_scent import _update_scent
from cop_worker.domain.types import DomainState
from cop_worker.rules_outcomes import GameOutcome


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
    cop_score: int
    thief_score: int
    error: str | None


def _finish(
    state: DomainState,
    *,
    turn: int,
    cop_position,
    thief_position,
    barriers,
    cop_barriers_remaining: int,
    move_history,
    outcome: GameOutcome,
    cop_action_legal: bool,
    thief_action_legal: bool,
    barrier_placed: bool,
    barrier_position,
    capture: bool,
    trapped: bool,
    cop_score: int,
    thief_score: int,
    error: str | None,
) -> TransitionResult:
    """Build the new DomainState (advancing both scent fields) + result."""
    g = state.grid_size
    new_state = DomainState(
        turn=turn,
        grid_size=g,
        cop_position=cop_position,
        thief_position=thief_position,
        barriers=barriers,
        cop_barriers_remaining=cop_barriers_remaining,
        move_history=move_history,
        cop_scent=_update_scent(state.cop_scent, cop_position, g),
        thief_scent=_update_scent(state.thief_scent, thief_position, g),
    )
    return TransitionResult(
        new_state=new_state,
        outcome=outcome,
        cop_action_legal=cop_action_legal,
        thief_action_legal=thief_action_legal,
        barrier_placed=barrier_placed,
        barrier_position=barrier_position,
        capture=capture,
        trapped=trapped,
        cop_score=cop_score,
        thief_score=thief_score,
        error=error,
    )
