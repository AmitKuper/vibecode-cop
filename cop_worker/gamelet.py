"""Gamelet lifecycle coordinator for cop_worker."""

from __future__ import annotations

import logging
from typing import Any

from cop_worker.board import Board
from cop_worker.commit_reveal import CommitRevealStateMachine
from cop_worker.gamelet_constants import (  # noqa: F401  (re-exports)
    _COP_ACTIONS,
    _GRID_SIZE,
    _MOVE_DELTAS,
    _POLICY_TO_GAMELET_COP,
    GameletError,
)
from cop_worker.gamelet_events import GameletEventMixin
from cop_worker.gamelet_moves import GameletMoveMixin
from cop_worker.gamelet_obs import GameletObservationMixin
from cop_worker.gamelet_results import GameletResultMixin
from cop_worker.observation_processor import ObservationProcessor
from cop_worker.parameter_registry import validate_terms
from cop_worker.rules_engine import RulesEngine
from cop_worker.state_machine import GameletState, GameletStateMachine

logger = logging.getLogger(__name__)


class Gamelet(
    GameletObservationMixin,
    GameletMoveMixin,
    GameletEventMixin,
    GameletResultMixin,
):
    """Coordinates the full lifecycle of one sub-game (gamelet).

    Owns: state machine, commit-reveal, nonces, audit record accumulation.
    Does NOT own: MCP transport, series lifecycle, Gmail reporting.
    """

    def __init__(
        self,
        game_uid: str,
        sub_game_number: int,
        terms: dict,
        opponent_group: str,
        role: str,
        belief_provider: Any = None,
        policy: Any = None,
    ) -> None:
        """Initialise gamelet and validate terms.

        Args:
            game_uid: Canonical series identity.
            sub_game_number: Sub-game index 1..6.
            terms: Full agreed terms dict.
            opponent_group: Opponent's group_id.
            role: This worker's role ("police" or "thief").
            belief_provider: BeliefEngine or SyntheticBeliefProvider instance.
            policy: Optional RecurrentRolePolicy for RL-driven move generation.

        Raises:
            GameletError: If terms fail validation.
        """
        violations = validate_terms(terms)
        if violations:
            raise GameletError(f"Term violations: {violations}")
        self.game_uid = game_uid
        self.sub_game_number = sub_game_number
        self.terms = terms
        self.opponent_group = opponent_group
        self.role = role
        self.belief_provider = belief_provider
        self._policy = policy
        self._grid_size = int(terms.get("board_size", _GRID_SIZE))
        # Tracked own position, seeded from agreed terms (NOT a placeholder). Advanced each
        # step by applying our own committed action via the canonical board transition, so the
        # RL policy observes where it actually is instead of a fixed centre-of-board stub.
        _start = terms.get("cop_start", [0, 0])
        self._own_position: tuple[int, int] = (int(_start[0]), int(_start[1]))
        self._known_barriers: list[list[int]] = []
        self._own_barriers_remaining: int = int(terms.get("barriers_max", 0))
        self._last_hint: str = ""
        # Highest step whose own-action we have already applied, so a retried/reordered
        # commit for the same step cannot advance us twice.
        self._advanced_through_step: int = 0
        # Latest opponent scent field as transmitted on the wire ({'r,c': v}); empty until the
        # first peer turn arrives. Fed into LocalObservation.opponent_scent so the cop can smell
        # the thief. Mirrors how RLMover consumes the peer's smell_grid on the reference-v3 wire.
        self._opponent_smell: dict[str, float] = {}
        # Board + RulesEngine used only to emit OUR own byte-exact book scent field (emitter cell
        # = our position). Sent on the wire so the opponent can smell us — symmetric with RLMover.
        self._smell_board = Board(
            cop_position=[0, 0],
            thief_position=[self._own_position[0], self._own_position[1]],
            grid_size=self._grid_size,
        )
        self._smell_rules = RulesEngine(
            self._smell_board, max_turns=int(terms.get("max_steps", 35))
        )
        self._sm = GameletStateMachine()
        # Terms already agreed — fast-path to LOCKED
        self._sm.transition(GameletState.NEGOTIATING)
        self._sm.transition(GameletState.LOCKED)
        self._step = 0
        self._audit_records: list[dict] = []
        self._result: dict | None = None
        self._audit_bundle: dict | None = None
        self._cr: CommitRevealStateMachine | None = None
        self._processor = ObservationProcessor()
        # Map step -> (nonce, action_dict) for our own pending reveals
        self._pending_reveals: dict[int, tuple[str, dict]] = {}
        logger.info("Gamelet %s sg%d initialised role=%s", game_uid[:8], sub_game_number, role)

    @property
    def state(self) -> GameletState:
        """Current gamelet state."""
        return self._sm.state

    def start_playing(self) -> None:
        """Transition to PLAYING state and initialise commit-reveal."""
        self._sm.transition(GameletState.PLAYING)
        self._cr = CommitRevealStateMachine(expected_step=1)
        # Per-step opponent commit storage for verify_reveal calls
        self._opponent_commits: dict[int, str] = {}

    def process_event(self, event_type: str, payload: dict) -> dict:
        """Dispatch an inbound event to the appropriate handler.

        Args:
            event_type: One of 'opponent_turn', 'opponent_audit', 'control_signal'.
            payload: Raw payload dict (already normalised by LM).

        Returns:
            Response payload dict to be forwarded to peer.
        """
        if event_type == "opponent_turn":
            return self._handle_turn(payload)
        if event_type == "opponent_audit":
            return self._handle_audit(payload)
        if event_type == "control_signal":
            return self._handle_control(payload)
        raise GameletError(f"Unknown event_type: {event_type!r}")
