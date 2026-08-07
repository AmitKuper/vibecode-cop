"""Tests for GameletStateMachine state transitions."""

import pytest

from cop_worker.state_machine import (
    TERMINAL_STATES,
    GameletState,
    GameletStateMachine,
    IllegalTransitionError,
)


def test_initial_state_is_created():
    """State machine must start in CREATED."""
    sm = GameletStateMachine()
    assert sm.state == GameletState.CREATED


def test_legal_transition_created_to_negotiating():
    """CREATED → NEGOTIATING must succeed."""
    sm = GameletStateMachine()
    sm.transition(GameletState.NEGOTIATING)
    assert sm.state == GameletState.NEGOTIATING


def test_illegal_transition_raises():
    """CREATED → PLAYING must raise IllegalTransitionError."""
    sm = GameletStateMachine()
    with pytest.raises(IllegalTransitionError):
        sm.transition(GameletState.PLAYING)


def test_is_terminal_false_in_playing():
    """PLAYING is not a terminal state."""
    sm = GameletStateMachine()
    sm.transition(GameletState.NEGOTIATING)
    sm.transition(GameletState.LOCKED)
    sm.transition(GameletState.PLAYING)
    assert sm.is_terminal() is False


def test_is_terminal_true_in_settled():
    """SETTLED is a terminal state."""
    sm = GameletStateMachine()
    sm.transition(GameletState.NEGOTIATING)
    sm.transition(GameletState.LOCKED)
    sm.transition(GameletState.PLAYING)
    sm.transition(GameletState.GAMEPLAY_TERMINAL)
    sm.transition(GameletState.AUDITING)
    sm.transition(GameletState.VERIFIED)
    sm.transition(GameletState.SETTLED)
    assert sm.is_terminal() is True


def test_all_terminal_states_covered():
    """SETTLED, TECHNICAL_FAILURE, TAMPERED, ABORTED must all be terminal."""
    for state in (
        GameletState.SETTLED,
        GameletState.TECHNICAL_FAILURE,
        GameletState.TAMPERED,
        GameletState.ABORTED,
    ):
        assert state in TERMINAL_STATES
