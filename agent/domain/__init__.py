"""Deterministic domain core — typed schemas and pure transition function."""

from agent.domain.config_validator import GameConfig, validate_game_config
from agent.domain.transition import TransitionResult, apply_joint_action
from agent.domain.types import (
    AuditSummary,
    BeliefState,
    CommitmentRecord,
    DomainState,
    GameletResult,
    LocalObservation,
    MoveRecord,
    PrivateState,
    ResultAgreement,
    RevealRecord,
)

__all__ = [
    "AuditSummary",
    "BeliefState",
    "CommitmentRecord",
    "DomainState",
    "GameConfig",
    "GameletResult",
    "LocalObservation",
    "MoveRecord",
    "PrivateState",
    "ResultAgreement",
    "RevealRecord",
    "TransitionResult",
    "apply_joint_action",
    "validate_game_config",
]
