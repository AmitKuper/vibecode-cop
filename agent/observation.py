"""Dec-POMDP observation types — explicit, immutable, role-filtered.

No opponent true position is ever present in LocalObservation or SafeLiveView.
BeliefState holds a Bayesian probability distribution over opponent location.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LocalObservation:
    """What one agent can legally see. No opponent true position."""

    own_position: tuple[int, int]  # own true position
    own_barriers_remaining: int  # for cop only; 0 for thief
    known_barriers: list[tuple[int, int]]  # public barrier list (sorted)
    opponent_scent: list[list[float]]  # opponent's scent field (NxN)
    last_hint: str  # last received free-language hint
    step: int
    gamelet: int
    grid_size: int
    # NOTE: no opponent_position field by design


@dataclass
class BeliefState:
    """Bayesian probability distribution over opponent position."""

    grid_size: int
    prob: np.ndarray  # shape (grid_size, grid_size), sums to 1.0
    entropy: float = 0.0
    confidence: float = 0.0
    step: int = 0

    @classmethod
    def uniform(cls, grid_size: int, step: int = 0) -> BeliefState:
        prob = np.ones((grid_size, grid_size)) / (grid_size * grid_size)
        return cls(
            grid_size=grid_size,
            prob=prob,
            entropy=float(np.log(grid_size * grid_size)),
            confidence=0.0,
            step=step,
        )

    def normalize(self) -> BeliefState:
        total = self.prob.sum()
        if total < 1e-10:
            return BeliefState.uniform(self.grid_size, self.step)
        normed = self.prob / total
        entropy = -float(np.sum(normed * np.log(normed + 1e-10)))
        confidence = float(1.0 / (1.0 + entropy))
        return BeliefState(self.grid_size, normed, entropy, confidence, self.step)

    def mask_barriers(self, barriers: list[tuple[int, int]]) -> BeliefState:
        new_prob = self.prob.copy()
        for x, y in barriers:
            if 0 <= x < self.grid_size and 0 <= y < self.grid_size:
                new_prob[y][x] = 0.0
        return BeliefState(
            self.grid_size, new_prob, self.entropy, self.confidence, self.step
        ).normalize()


@dataclass(frozen=True)
class SafeLiveView:
    """Role-filtered view for GUI. Contains no hidden opponent coordinate."""

    own_position: tuple[int, int]
    belief_heatmap: list[list[float]]  # prob matrix as list-of-lists
    opponent_scent: list[list[float]]
    last_hint: str
    hint_reliability: float
    turn: int
    gamelet: int
    score: dict  # {"cop": int, "thief": int}
    own_barriers_remaining: int
    protocol_state: str
    your_turn: bool
    connection_healthy: bool
