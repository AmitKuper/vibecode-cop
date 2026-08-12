"""Shared helpers for the recurrent-training evidence-contract test modules."""

from cop_worker.domain.types import DomainState


def _state(*, turn: int = 0, cop=(0, 0), thief=(2, 2)) -> DomainState:
    return DomainState(
        turn=turn,
        grid_size=7,
        cop_position=cop,
        thief_position=thief,
        barriers=[],
        cop_barriers_remaining=14,
        move_history=[],
        scent_grid=[[0.0] * 7 for _ in range(7)],
    )
