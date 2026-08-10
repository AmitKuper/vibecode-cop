"""Gamelet audit preparation, result construction, and shutdown (mixin)."""

from __future__ import annotations

import logging

from cop_worker.gamelet_constants import GameletError
from cop_worker.language.llm_hint import token_totals as llm_token_totals
from cop_worker.state_machine import GameletState

logger = logging.getLogger(__name__)


class GameletResultMixin:
    """Audit records, final result, and teardown."""

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
            "llm_tokens": llm_token_totals(),
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
