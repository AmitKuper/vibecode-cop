"""Gamelet-level state machine for cop_worker."""

from __future__ import annotations

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class GameletState(StrEnum):
    """All valid states in the gamelet lifecycle."""

    CREATED = "CREATED"
    NEGOTIATING = "NEGOTIATING"
    LOCKED = "LOCKED"
    PLAYING = "PLAYING"
    GAMEPLAY_TERMINAL = "GAMEPLAY_TERMINAL"
    AUDITING = "AUDITING"
    VERIFIED = "VERIFIED"
    SETTLED = "SETTLED"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
    TAMPERED = "TAMPERED"
    ABORTED = "ABORTED"


TERMINAL_STATES = {
    GameletState.SETTLED,
    GameletState.TECHNICAL_FAILURE,
    GameletState.TAMPERED,
    GameletState.ABORTED,
}

LEGAL_TRANSITIONS: dict[GameletState, set[GameletState]] = {
    GameletState.CREATED: {GameletState.NEGOTIATING, GameletState.ABORTED},
    GameletState.NEGOTIATING: {
        GameletState.LOCKED,
        GameletState.ABORTED,
        GameletState.TECHNICAL_FAILURE,
    },
    GameletState.LOCKED: {
        GameletState.PLAYING,
        GameletState.ABORTED,
        GameletState.TECHNICAL_FAILURE,
    },
    GameletState.PLAYING: {
        GameletState.GAMEPLAY_TERMINAL,
        GameletState.TECHNICAL_FAILURE,
        GameletState.ABORTED,
    },
    GameletState.GAMEPLAY_TERMINAL: {
        GameletState.AUDITING,
        GameletState.TECHNICAL_FAILURE,
    },
    GameletState.AUDITING: {
        GameletState.VERIFIED,
        GameletState.TAMPERED,
        GameletState.TECHNICAL_FAILURE,
    },
    GameletState.VERIFIED: {GameletState.SETTLED},
    GameletState.SETTLED: set(),
    GameletState.TECHNICAL_FAILURE: set(),
    GameletState.TAMPERED: set(),
    GameletState.ABORTED: set(),
}


class IllegalTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""


class GameletStateMachine:
    """Manages gamelet lifecycle state transitions.

    Enforces legal state progression from CREATED to a terminal state.
    All illegal transitions raise IllegalTransitionError with both states logged.
    """

    def __init__(self) -> None:
        """Initialise state machine in CREATED state."""
        self._state = GameletState.CREATED

    @property
    def state(self) -> GameletState:
        """Current gamelet state."""
        return self._state

    def transition(self, new_state: GameletState) -> None:
        """Attempt a state transition.

        Args:
            new_state: Target state to transition to.

        Raises:
            IllegalTransitionError: If transition is not permitted from current state.
        """
        allowed = LEGAL_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            msg = f"Illegal transition {self._state} -> {new_state}"
            logger.error(msg)
            raise IllegalTransitionError(msg)
        logger.info("Gamelet transition: %s -> %s", self._state, new_state)
        self._state = new_state

    def is_terminal(self) -> bool:
        """Return True if the current state is a terminal state."""
        return self._state in TERMINAL_STATES
