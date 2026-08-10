"""Observation-side domain types: local observation and belief state."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class LocalObservation(BaseModel):
    """What a strategy policy or LLM receives — no hidden opponent state.

    Contains own position, known barriers, opponent scent field,
    and the most recent natural-language hint from the opponent.
    """

    own_position: tuple[int, int]
    turn: int
    max_turns: int = 35
    grid_size: int = 7
    barriers: list[tuple[int, int]] = Field(default_factory=list)
    barriers_remaining: int = 14
    opponent_scent: list[list[float]] = Field(default_factory=list)
    last_hint: str | None = None
    candidate_actions: list[str] = Field(default_factory=list)
    role: str = ""


class BeliefState(BaseModel):
    """Normalized probability distribution over opponent grid location.

    distribution[y][x] is the probability that the opponent is at (x, y).
    Sum of all values must be 1.0 (within tolerance).
    """

    grid_size: int = 7
    distribution: list[list[float]] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    turn: int = 0
    last_scent_update: int = -1

    @model_validator(mode="after")
    def _initialize_uniform_if_empty(self) -> BeliefState:
        if not self.distribution:
            g = self.grid_size
            uniform = 1.0 / (g * g)
            self.distribution = [[uniform] * g for _ in range(g)]
        return self

    @classmethod
    def uniform(cls, grid_size: int = 7) -> BeliefState:
        """Return a uniform prior over all grid cells."""
        return cls(grid_size=grid_size)
