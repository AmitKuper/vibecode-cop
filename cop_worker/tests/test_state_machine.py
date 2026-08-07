"""Tests for cop_worker.state_machine — legal and illegal transitions."""

from __future__ import annotations

import pytest

from cop_worker.state_machine import (
    TERMINAL_STATES,
    GameletState,
    GameletStateMachine,
    IllegalTransitionError,
)


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        (GameletState.CREATED, GameletState.NEGOTIATING),
        (GameletState.NEGOTIATING, GameletState.LOCKED),
        (GameletState.LOCKED, GameletState.PLAYING),
        (GameletState.PLAYING, GameletState.GAMEPLAY_TERMINAL),
        (GameletState.GAMEPLAY_TERMINAL, GameletState.AUDITING),
        (GameletState.AUDITING, GameletState.VERIFIED),
        (GameletState.VERIFIED, GameletState.SETTLED),
        (GameletState.PLAYING, GameletState.TECHNICAL_FAILURE),
        (GameletState.AUDITING, GameletState.TAMPERED),
        (GameletState.NEGOTIATING, GameletState.ABORTED),
    ],
)
def test_legal_transition(from_state: GameletState, to_state: GameletState) -> None:
    """All legal transitions must succeed without raising."""
    sm = GameletStateMachine()
    sm._state = from_state
    sm.transition(to_state)
    assert sm.state == to_state


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        (GameletState.CREATED, GameletState.PLAYING),
        (GameletState.CREATED, GameletState.SETTLED),
        (GameletState.PLAYING, GameletState.SETTLED),
        (GameletState.SETTLED, GameletState.PLAYING),
        (GameletState.SETTLED, GameletState.TECHNICAL_FAILURE),
        (GameletState.TECHNICAL_FAILURE, GameletState.PLAYING),
        (GameletState.GAMEPLAY_TERMINAL, GameletState.PLAYING),
        (GameletState.AUDITING, GameletState.PLAYING),
        (GameletState.VERIFIED, GameletState.AUDITING),
    ],
)
def test_illegal_transition_raises(from_state: GameletState, to_state: GameletState) -> None:
    """All illegal transitions must raise IllegalTransitionError."""
    sm = GameletStateMachine()
    sm._state = from_state
    with pytest.raises(IllegalTransitionError):
        sm.transition(to_state)


@pytest.mark.parametrize(
    "terminal_state",
    [
        GameletState.SETTLED,
        GameletState.TECHNICAL_FAILURE,
        GameletState.TAMPERED,
        GameletState.ABORTED,
    ],
)
def test_is_terminal_true_for_all_terminal_states(
    terminal_state: GameletState,
) -> None:
    """is_terminal() returns True for all terminal states."""
    sm = GameletStateMachine()
    sm._state = terminal_state
    assert sm.is_terminal() is True


@pytest.mark.parametrize(
    "non_terminal_state",
    [
        GameletState.CREATED,
        GameletState.NEGOTIATING,
        GameletState.LOCKED,
        GameletState.PLAYING,
        GameletState.GAMEPLAY_TERMINAL,
        GameletState.AUDITING,
        GameletState.VERIFIED,
    ],
)
def test_is_terminal_false_for_non_terminal_states(
    non_terminal_state: GameletState,
) -> None:
    """is_terminal() returns False for all non-terminal states."""
    sm = GameletStateMachine()
    sm._state = non_terminal_state
    assert sm.is_terminal() is False


def test_initial_state_is_created() -> None:
    """State machine starts in CREATED state."""
    sm = GameletStateMachine()
    assert sm.state == GameletState.CREATED


def test_terminal_states_set_matches_constant() -> None:
    """TERMINAL_STATES constant covers exactly the four terminal states."""
    assert {
        GameletState.SETTLED,
        GameletState.TECHNICAL_FAILURE,
        GameletState.TAMPERED,
        GameletState.ABORTED,
    } == TERMINAL_STATES


def test_full_happy_path_transitions() -> None:
    """Full happy path from CREATED through all states to SETTLED."""
    sm = GameletStateMachine()
    path = [
        GameletState.NEGOTIATING,
        GameletState.LOCKED,
        GameletState.PLAYING,
        GameletState.GAMEPLAY_TERMINAL,
        GameletState.AUDITING,
        GameletState.VERIFIED,
        GameletState.SETTLED,
    ]
    for state in path:
        sm.transition(state)
    assert sm.state == GameletState.SETTLED
    assert sm.is_terminal() is True
