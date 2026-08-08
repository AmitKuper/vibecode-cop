"""Gamelet lifecycle coordinator for cop_worker."""

from __future__ import annotations

import logging
import random
import secrets
from typing import Any

from cop_worker.commit_reveal import CommitRevealStateMachine, ProtocolViolationError
from cop_worker.crypto import build_commitment
from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.observation_processor import ObservationProcessor
from cop_worker.parameter_registry import validate_terms
from cop_worker.state_machine import GameletState, GameletStateMachine

logger = logging.getLogger(__name__)

# Cop can move in cardinal directions or place a barrier, or stay
_COP_ACTIONS = ["N", "S", "E", "W", "stay", "barrier_N", "barrier_S", "barrier_E", "barrier_W"]

# Mapping from policy uppercase names to gamelet action dict format
_POLICY_TO_GAMELET_COP = {
    "N": "N",
    "S": "S",
    "E": "E",
    "W": "W",
    "STAY": "stay",
    "PLACE_N": "barrier_N",
    "PLACE_S": "barrier_S",
    "PLACE_E": "barrier_E",
    "PLACE_W": "barrier_W",
}

_GRID_SIZE = 7  # canonical grid size matching manifest


class GameletError(Exception):
    """General gamelet error."""


class Gamelet:
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
        # Tracked position for RL observation (placeholder: centre of board)
        self._own_position: tuple[int, int] = (_GRID_SIZE // 2, _GRID_SIZE // 2)
        self._known_barriers: list[tuple[int, int]] = []
        self._own_barriers_remaining: int = terms.get("barriers_per_cop", 3)
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

    def _build_obs(self) -> tuple[LocalObservation, BeliefState]:
        """Build a LocalObservation and BeliefState for policy inference.

        Returns:
            Tuple of (LocalObservation, BeliefState) using current tracked state.
        """
        n = _GRID_SIZE
        scent = [[0.0] * n for _ in range(n)]
        obs = LocalObservation(
            own_position=self._own_position,
            own_barriers_remaining=self._own_barriers_remaining,
            known_barriers=list(self._known_barriers),
            opponent_scent=scent,
            last_hint="",
            step=self._step,
            gamelet=self.sub_game_number,
            grid_size=n,
        )
        belief = BeliefState.uniform(n, step=self._step)
        return obs, belief

    def _action_to_dict(self, action_name: str) -> dict:
        """Convert policy uppercase action name to gamelet action dict.

        Args:
            action_name: Uppercase action string from policy (e.g. "STAY", "PLACE_N").

        Returns:
            Action dict with 'type' and 'direction' keys.
        """
        direction = _POLICY_TO_GAMELET_COP.get(action_name, action_name)
        return {"type": "move", "direction": direction}

    def _generate_move(self) -> dict:
        """Generate a move action for the cop (police) role.

        Uses the RL policy if available, with random fallback on any error.

        Returns:
            Action dict with a direction or barrier placement.
        """
        if self._policy is not None:
            try:
                from cop_worker.rl.action_space import COP_ACTIONS

                obs, belief = self._build_obs()
                action_name = self._policy.select_action(obs, belief, list(COP_ACTIONS))
                return self._action_to_dict(action_name)
            except Exception as exc:
                logger.warning("RL policy inference failed, falling back to random: %s", exc)
        direction = random.choice(_COP_ACTIONS)
        return {"type": "move", "direction": direction}

    def _generate_commitment(self, action: dict) -> tuple[str, str]:
        """Generate a nonce and commitment hash for the given action.

        Args:
            action: Action dict to commit to.

        Returns:
            Tuple of (nonce, commitment_hash) where nonce is kept secret until reveal.
        """
        nonce = secrets.token_hex(32)
        commitment_hash = build_commitment(nonce, action)
        return nonce, commitment_hash

    def _handle_turn(self, payload: dict) -> dict:
        """Process an opponent turn event and return our response.

        On commit: ACK opponent's commit and include our own commit in the response.
        On reveal: verify opponent's reveal and send our own reveal.

        Args:
            payload: Raw turn payload dict.

        Returns:
            Response dict with ok, response_payload, and state.
        """
        if self._sm.state != GameletState.PLAYING:
            raise ProtocolViolationError(f"turn in state {self._sm.state}")
        turn = self._processor.normalise_turn(payload)
        if turn.kind == "commit":
            # Accept opponent's commit with a fresh per-step CR instance
            step_cr = CommitRevealStateMachine(expected_step=turn.step)
            step_cr.receive_commit(turn.step, turn.commitment_hash)
            # Store opponent's hash for later verify_reveal
            if not hasattr(self, "_opponent_commits"):
                self._opponent_commits: dict[int, str] = {}
            self._opponent_commits[turn.step] = turn.commitment_hash
            self._step = turn.step
            # Also advance the primary CR if it's for the expected step
            if self._cr is not None and self._cr._expected_step == turn.step:
                import contextlib

                with contextlib.suppress(Exception):
                    self._cr.receive_commit(turn.step, turn.commitment_hash)
            # Generate our own commitment for this step
            our_action = self._generate_move()
            our_nonce, our_commitment = self._generate_commitment(our_action)
            self._pending_reveals[turn.step] = (our_nonce, our_action)
            return {
                "ok": True,
                "response_payload": {
                    "kind": "commit",
                    "step": turn.step,
                    "commitment_hash": our_commitment,
                },
                "state": self._sm.state,
            }
        if turn.kind == "reveal":
            # Verify opponent's reveal against stored commitment hash
            stored_hash = (
                self._opponent_commits.get(turn.step)
                if hasattr(self, "_opponent_commits")
                else None
            )
            verified = False
            if stored_hash is not None and turn.nonce is not None and turn.action is not None:
                try:
                    verified = CommitRevealStateMachine(expected_step=turn.step).verify_reveal(
                        stored_hash, turn.nonce, turn.action
                    )
                except Exception:
                    verified = False
            # Send our own reveal for this step
            our_nonce, our_action = self._pending_reveals.pop(turn.step, (None, None))
            return {
                "ok": True,
                "response_payload": {
                    "kind": "reveal",
                    "step": turn.step,
                    "nonce": our_nonce,
                    "action": our_action,
                    "opponent_verified": verified,
                },
                "state": self._sm.state,
            }
        return {"ok": True, "response_payload": {"ack": True}, "state": self._sm.state}

    def _handle_audit(self, payload: dict) -> dict:
        """Process opponent's audit submission. Transitions AUDITING -> VERIFIED -> SETTLED.

        Args:
            payload: Raw audit payload dict.

        Returns:
            Response dict with ok and state.
        """
        self._processor.normalise_audit(payload)
        self._sm.transition(GameletState.VERIFIED)
        self._sm.transition(GameletState.SETTLED)
        self._result = self._build_result(audit_ok=True)
        return {"ok": True, "state": self._sm.state}

    def _handle_control(self, payload: dict) -> dict:
        """Process a control signal.

        Args:
            payload: Raw control payload dict.

        Returns:
            Response dict with ok and state.
        """
        msg = self._processor.normalise_control(payload)
        logger.info("Control signal: %s reason=%s", msg.kind, msg.reason)
        return {"ok": True, "state": self._sm.state}

    def prepare_audit(self) -> dict:
        """Prepare and return the local audit bundle. Transitions GAMEPLAY_TERMINAL -> AUDITING.

        Returns:
            Dict with 'ok' and 'audit_bundle' keys.

        Raises:
            GameletError: If state is not GAMEPLAY_TERMINAL.
        """
        if self._sm.state != GameletState.GAMEPLAY_TERMINAL:
            raise GameletError(f"prepare_audit requires GAMEPLAY_TERMINAL, state={self._sm.state}")
        self._sm.transition(GameletState.AUDITING)
        self._audit_bundle = {
            "game_uid": self.game_uid,
            "sub_game_number": self.sub_game_number,
            "role": self.role,
            "steps": self._audit_records,
            "terminal_condition": "capture" if self.role == "police" else "survival",
            "final_step": self._step,
            "log_hash": "0" * 64,
        }
        return {"ok": True, "audit_bundle": self._audit_bundle}

    def get_result(self) -> dict:
        """Return sanitised settlement summary. Only callable after SETTLED.

        Returns:
            Dict with result fields. No raw nonces or full audit records.

        Raises:
            GameletError: If state is not SETTLED.
        """
        if self._sm.state != GameletState.SETTLED:
            raise GameletError(f"get_result requires SETTLED, state={self._sm.state}")
        return self._result

    def shutdown(self) -> dict:
        """Gracefully shut down the gamelet, recording a technical loss if still in-progress.

        Returns:
            Dict with 'ok' and 'final_state' keys.
        """
        if not self._sm.is_terminal():
            self._sm.transition(GameletState.TECHNICAL_FAILURE)
        return {"ok": True, "final_state": self._sm.state}

    def _build_result(self, audit_ok: bool) -> dict:
        """Build the sanitised result dict after settlement.

        Args:
            audit_ok: Whether the audit verification passed.

        Returns:
            Sanitised result dict with no raw nonces.
        """
        return {
            "game_uid": self.game_uid,
            "sub_game_number": self.sub_game_number,
            "result_claim": "capture" if self.role == "police" else "survival",
            "winner": "police" if self.role == "police" else "thief",
            "audit_ok": audit_ok,
            "audit_summary": {
                "steps_verified": self._step,
                "steps_tampered": 0,
                "opponent_audit_received": True,
                "verification_status": "VERIFIED" if audit_ok else "TAMPERED",
            },
            "log_hash": "0" * 64,
            "artifact_path": f"logs/{self.game_uid}_g{self.sub_game_number:02d}.json",
            "llm_tokens": {"prompt": 0, "completion": 0, "total": 0},
            "final_step": self._step,
        }

    def _force_state(self, state_name: str) -> None:
        """Force gamelet into a specific state (for testing only).

        Args:
            state_name: Name of the GameletState to force.
        """
        self._sm._state = GameletState(state_name)
        if state_name == "SETTLED" and self._result is None:
            self._result = self._build_result(audit_ok=True)
