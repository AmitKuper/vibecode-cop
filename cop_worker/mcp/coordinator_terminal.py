"""Terminal transitions and cleanup of the protocol coordinator (mixin)."""

from __future__ import annotations

import contextlib
import logging
import time

from cop_worker.mcp.protocol import ProtocolState
from cop_worker.reliability.durable_io import atomic_write_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class CoordinatorTerminalMixin:
    """Audit, terminal-outcome, and cleanup transitions."""

    def on_audit_begin(self, game_id: str, gamelet: int, role: str) -> None:
        """Advance STEP_VERIFIED → AUDITING."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.STEP_VERIFIED:
                sm.transition(ProtocolState.AUDITING)

    def on_final_audit_complete(self, game_id: str, gamelet: int, role: str) -> None:
        """Advance AUDITING → RESULT_AGREEMENT."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.AUDITING:
                sm.transition(ProtocolState.RESULT_AGREEMENT)

    def on_done(self, game_id: str, gamelet: int, role: str) -> None:
        """Advance RESULT_AGREEMENT → REPORTING → DONE."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.RESULT_AGREEMENT:
                sm.transition(ProtocolState.REPORTING)
            if sm.state == ProtocolState.REPORTING:
                sm.transition(ProtocolState.DONE)

    def on_technical_loss(
        self,
        game_id: str,
        gamelet: int,
        role: str,
        reason: str = "",
        evidence: dict | None = None,
        evidence_path: str | None = None,
    ) -> None:
        """Advance to TECHNICAL_LOSS and durably record the controlled outcome."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock, contextlib.suppress(ValueError):
            entry.sm.transition(ProtocolState.TECHNICAL_LOSS)
        if evidence_path:
            atomic_write_json(
                evidence_path,
                {
                    "schema_version": "1.0",
                    "game_id": game_id,
                    "gamelet": gamelet,
                    "role": role,
                    "protocol_state": ProtocolState.TECHNICAL_LOSS.value,
                    "reason": reason,
                    "evidence": evidence or {},
                    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
        if reason:
            logger.error(
                "[Coordinator] TECHNICAL_LOSS %s gamelet=%d %s: %s evidence=%s",
                game_id,
                gamelet,
                role,
                reason,
                evidence,
            )

    def cleanup_session(self, game_id: str, gamelet: int, role: str) -> None:
        """Remove session from registry after it reaches a terminal state.

        Terminal states: DONE, ABORTED, TECHNICAL_LOSS.
        Idempotent: if the session does not exist, does nothing.
        """
        state = self._registry.state_of(game_id, gamelet, role)
        if state in (
            ProtocolState.DONE,
            ProtocolState.TECHNICAL_LOSS,
            ProtocolState.ABORTED,
            None,
        ):
            self._registry.remove(game_id, gamelet, role)
            # Also purge idempotency records for this session to free memory
            with self._idempotency_lock:
                keys_to_remove = [
                    k
                    for k in self._idempotency
                    if k[0] == game_id and k[1] == gamelet and k[2] == role
                ]
                for k in keys_to_remove:
                    del self._idempotency[k]
            logger.info(
                "[Coordinator] Session cleaned up: %s gamelet=%d %s (state was %s)",
                game_id,
                gamelet,
                role,
                state.value if state else "None",
            )
        else:
            logger.warning(
                "[Coordinator] cleanup_session called but state is %s (non-terminal) for %s",
                state.value if state else "None",
                game_id,
            )
