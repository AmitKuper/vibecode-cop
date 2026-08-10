"""Outbound notify helpers - thin wrappers around the coordinator for callers
that hold a game_id/gamelet/role tuple."""

from __future__ import annotations

from cop_worker.mcp.coordinator import get_coordinator


def notify_commit_sent(game_id: str, gamelet: int, role: str, step: int) -> None:
    """Called by the orchestrator after it sends its commit to the peer."""
    get_coordinator().on_commit_exchange_complete(game_id, gamelet, role, step)


def notify_reveal_sent(game_id: str, gamelet: int, role: str, step: int) -> None:
    """Called by the orchestrator after it sends its reveal to the peer."""
    get_coordinator().on_reveal_exchange_complete(game_id, gamelet, role, step)


def notify_step_begin(game_id: str, gamelet: int, role: str, step: int = 0) -> None:
    """Called at the start of each step — READY/STEP_VERIFIED → COMPUTING_MOVE."""
    get_coordinator().begin_step(game_id, gamelet, role, step)


def notify_audit_begin(game_id: str, gamelet: int, role: str) -> None:
    """Advance STEP_VERIFIED → AUDITING."""
    get_coordinator().on_audit_begin(game_id, gamelet, role)


def notify_done(game_id: str, gamelet: int, role: str) -> None:
    """Advance → DONE."""
    get_coordinator().on_done(game_id, gamelet, role)


def notify_technical_loss(game_id: str, gamelet: int, role: str, reason: str = "") -> None:
    """Transition any non-terminal → TECHNICAL_LOSS."""
    get_coordinator().on_technical_loss(game_id, gamelet, role, reason=reason)
