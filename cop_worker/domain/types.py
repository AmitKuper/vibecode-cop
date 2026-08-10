"""Typed schemas for the Cop-Thief P2P domain.

These models define strict information boundaries:
  - DomainState: full game state (both positions, all barriers, scent)
  - PrivateState: local-only data (nonces) — never serialized to opponent
  - LocalObservation: what strategy/RL/LLM receives (own position + opponent scent)
  - BeliefState: probability distribution over opponent location
  - CommitmentRecord, RevealRecord: commit-reveal protocol records
  - AuditSummary, ResultAgreement: final integrity records
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class MoveRecord(BaseModel):
    """One completed turn recorded in move_history."""

    turn: int
    cop_move: str
    thief_move: str
    cop_position: tuple[int, int]
    thief_position: tuple[int, int]


class DomainState(BaseModel):
    """Complete authoritative game state.

    Holds both positions (only available inside the protocol/verification engine).
    Must never be passed to strategy, LLM, or GUI APIs.
    """

    turn: int = Field(ge=0)
    grid_size: int = Field(ge=3, le=20, default=7)
    cop_position: tuple[int, int]
    thief_position: tuple[int, int]
    barriers: list[tuple[int, int]] = Field(default_factory=list)
    cop_barriers_remaining: int = Field(ge=0, default=14)
    move_history: list[MoveRecord] = Field(default_factory=list)
    cop_scent: list[list[float]] = Field(default_factory=list)
    thief_scent: list[list[float]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_scent(cls, value):
        """Accept old serialized state while keeping one dual-scent authority."""
        if isinstance(value, dict) and "scent_grid" in value:
            migrated = dict(value)
            legacy = migrated.pop("scent_grid")
            migrated.setdefault("thief_scent", legacy)
            migrated.setdefault("cop_scent", [])
            return migrated
        return value

    @model_validator(mode="after")
    def _validate_positions(self) -> DomainState:
        g = self.grid_size
        for label, pos in [("cop", self.cop_position), ("thief", self.thief_position)]:
            x, y = pos
            if not (0 <= x < g and 0 <= y < g):
                raise ValueError(f"{label}_position {pos} is out of bounds for grid_size={g}")
        for i, b in enumerate(self.barriers):
            x, y = b
            if not (0 <= x < g and 0 <= y < g):
                raise ValueError(f"barrier[{i}] {b} is out of bounds for grid_size={g}")
        return self

    @property
    def scent_grid(self) -> list[list[float]]:
        """Read-only compatibility alias for the historical thief scent field."""
        return self.thief_scent

    @classmethod
    def from_board(cls, board) -> DomainState:
        """Create from a Board instance (cop and thief positions available)."""
        return cls(
            turn=board.turn,
            grid_size=board.grid_size,
            cop_position=tuple(board.cop_position),
            thief_position=tuple(board.thief_position),
            barriers=[tuple(b) for b in board.barriers],
            move_history=[MoveRecord(**r) for r in board.move_history]
            if board.move_history
            else [],
        )

    def to_board_dict(self) -> dict:
        """Serialize to the legacy Board dict format for compatibility."""
        return {
            "turn": self.turn,
            "grid_size": self.grid_size,
            "cop_position": list(self.cop_position),
            "thief_position": list(self.thief_position),
            "barriers": [list(b) for b in self.barriers],
            "move_history": [r.model_dump() for r in self.move_history],
        }


class PrivateState(BaseModel):
    """Local-only data that must never be serialized to the opponent.

    Contains nonces for the current game — revealed only during final audit.
    """

    game_id: str
    role: str
    my_nonces: dict[int, str] = Field(default_factory=dict)
    my_commits: dict[int, str] = Field(default_factory=dict)
    my_reveals: dict[int, dict] = Field(default_factory=dict)


from cop_worker.domain.types_observation import (  # noqa: E402,F401  (re-exports)
    BeliefState,
    LocalObservation,
)
from cop_worker.domain.types_records import (  # noqa: E402,F401  (re-exports)
    AuditSummary,
    CommitmentRecord,
    GameletResult,
    ResultAgreement,
    RevealRecord,
)
