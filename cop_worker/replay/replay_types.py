"""Replay data types shared by the verification and reconstruction mixins."""

from __future__ import annotations

from dataclasses import dataclass

from cop_worker.audit.step_journal import StepEvidence

_GAMELETS = set(range(1, 7))


@dataclass
class ReplayState:
    game_uid: str
    gamelet: int
    step: int
    total_steps: int
    event: StepEvidence | None
    verified: bool
    tamper_reason: str
    transcript_verified: bool
    canonical_state: dict | None = None


class ReplayError(ValueError):
    pass
