"""Tabular Q policy: discretized state key and greedy serving wrapper."""

from __future__ import annotations

import random

import numpy as np

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.rl.research_value_training.networks import _actions
from cop_worker.rl.train_recurrent import _legal
from cop_worker.scent import ScentFields


def _q_key(state: DomainState, role: str, belief: BeliefEngine) -> tuple[int, ...]:
    own = state.cop_position if role == "cop" else state.thief_position
    target_index = int(belief.belief.prob.argmax())
    target = (target_index % state.grid_size, target_index // state.grid_size)
    barriers = set(state.barriers)
    adjacency = sum(
        1 << index
        for index, (dx, dy) in enumerate(((0, -1), (0, 1), (1, 0), (-1, 0)))
        if (own[0] + dx, own[1] + dy) in barriers
        or not (0 <= own[0] + dx < 7 and 0 <= own[1] + dy < 7)
    )
    return (
        own[0],
        own[1],
        target[0],
        target[1],
        min(state.turn // 5, 6),
        min(int(belief.belief.confidence * 10), 9),
        adjacency,
        min(state.cop_barriers_remaining // 3, 4) if role == "cop" else 0,
    )


class TabularResearchPolicy:
    def __init__(self, q_values: dict[tuple[int, ...], np.ndarray], role: str) -> None:
        self.q_values = q_values
        self.role = role

    def reset(self, seed: int) -> None:
        del seed

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        del scent, rng, gamelet
        actions = _actions(self.role)
        legal = _legal(state, self.role)
        values = self.q_values.get(_q_key(state, self.role, belief), np.zeros(len(actions)))
        return max(
            legal,
            key=lambda action: (
                float(values[actions.index(action)]),
                -actions.index(action),
            ),
        )
