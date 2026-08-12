"""Shared helpers for the ported protocol state machine test suites."""

from __future__ import annotations

from cop_worker.mcp.protocol import ProtocolState, ProtocolStateMachine


def fresh_sm() -> ProtocolStateMachine:
    return ProtocolStateMachine()


def advance_to(sm: ProtocolStateMachine, *states: ProtocolState) -> None:
    """Transition through a sequence of states."""
    for s in states:
        sm.transition(s)
