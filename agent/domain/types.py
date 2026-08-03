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

from typing import Literal

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
    scent_grid: list[list[float]] = Field(default_factory=list)

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


class CommitmentRecord(BaseModel):
    """Record of a single step commitment (received from opponent)."""

    game_id: str
    gamelet: int = 1
    step: int
    role: str
    h_commit: str
    received_at: str = ""


class RevealRecord(BaseModel):
    """Reveal received from opponent — nonce NOT included.

    The nonce is kept in PrivateState until final audit.
    Nonce must never appear in a RevealRecord that is exchanged during play.
    """

    game_id: str
    gamelet: int = 1
    step: int
    role: str
    move: str
    hint: str
    intent: str
    state_hash: str
    # nonce deliberately absent — see PrivateState


class AuditSummary(BaseModel):
    """Per-game audit result produced by run_final_audit()."""

    game_id: str
    gamelet: int = 1
    audit_status: Literal["PASSED", "FAILED", "NOT_APPLICABLE"]
    expected_steps: int = 0
    verified_steps: int = 0
    failed_steps: int = 0
    offending_role: str | None = None
    evidence_ref: str | None = None
    step_details: dict[str, str] = Field(default_factory=dict)


class GameletResult(BaseModel):
    """Score for one gamelet in a series."""

    gamelet: str
    game_id: str
    winner: str
    audit_ok: bool
    cop_pts: int
    thief_pts: int
    final_step: int


class ResultAgreement(BaseModel):
    """Signed series result — produced only after bilateral audit agreement."""

    series_id: str
    game_id: str
    cop_total: int
    thief_total: int
    series_winner: Literal["cop", "thief", "tie"]
    counted: bool
    gamelet_results: list[GameletResult] = Field(default_factory=list)
    audit_summaries: list[AuditSummary] = Field(default_factory=list)
    transcript_root: str = ""
    config_hash: str = ""
