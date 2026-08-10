"""Wire/audit record types: commitments, reveals, audits, results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
