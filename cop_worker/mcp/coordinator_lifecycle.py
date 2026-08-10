"""Lifecycle transitions of the protocol coordinator (mixin)."""

from __future__ import annotations

import logging

from cop_worker.mcp.protocol import ProtocolState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class CoordinatorLifecycleMixin:
    """Handshake, step, audit, terminal, and cleanup transitions."""

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------

    def on_handshake_complete(self, game_id: str, gamelet: int, role: str) -> None:
        """Advance local SM to READY after start_game is successfully sent or received.

        Idempotent: if already READY, does nothing.
        """
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.READY:
                return  # Already done (idempotent)
            if sm.state not in (ProtocolState.IDLE, ProtocolState.STEP0_NEGOTIATING):
                logger.warning(
                    "[Coordinator] on_handshake_complete called in state %s for %s",
                    sm.state.value,
                    game_id,
                )
                return
            if sm.state == ProtocolState.IDLE:
                sm.transition(ProtocolState.STEP0_NEGOTIATING)
            sm.transition(ProtocolState.READY)
            logger.info(
                "[Coordinator] Handshake complete → READY for %s gamelet=%d %s",
                game_id,
                gamelet,
                role,
            )

    # ------------------------------------------------------------------
    # Outbound lifecycle (active / cop side)
    # ------------------------------------------------------------------

    def begin_step(self, game_id: str, gamelet: int, role: str, step: int) -> None:
        """Advance READY or STEP_VERIFIED → COMPUTING_MOVE at start of a step.

        No-op if already in COMPUTING_MOVE or a terminal state.
        """
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state in (ProtocolState.READY, ProtocolState.STEP_VERIFIED):
                if sm.state == ProtocolState.STEP_VERIFIED:
                    sm.advance_step()
                sm.transition(ProtocolState.COMPUTING_MOVE)
                logger.debug("[Coordinator] begin_step %s step=%d → COMPUTING_MOVE", game_id, step)

    def on_commit_exchange_complete(self, game_id: str, gamelet: int, role: str, step: int) -> None:
        """Advance COMPUTING_MOVE → COMMIT_SENT → BOTH_COMMITTED.

        Called after a synchronous commit exchange where we send our commit and
        the peer immediately returns their commit in the same HTTP response.
        """
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.COMPUTING_MOVE:
                sm.transition(ProtocolState.COMMIT_SENT)
                sm.transition(ProtocolState.BOTH_COMMITTED)
                entry.commit_sent_step = step
                logger.debug(
                    "[Coordinator] commit_exchange_complete %s step=%d → BOTH_COMMITTED",
                    game_id,
                    step,
                )
            elif sm.state == ProtocolState.COMMIT_RECEIVED:
                # Peer committed first; we just sent ours
                sm.transition(ProtocolState.BOTH_COMMITTED)
                entry.commit_sent_step = step
            elif sm.state == ProtocolState.BOTH_COMMITTED:
                pass  # idempotent
            else:
                logger.warning(
                    "[Coordinator] on_commit_exchange_complete: unexpected state %s", sm.state.value
                )

    def on_reveal_exchange_complete(self, game_id: str, gamelet: int, role: str, step: int) -> None:
        """Advance BOTH_COMMITTED → REVEAL_SENT → STEP_VERIFIED."""
        entry = self._registry.get_or_create(game_id, gamelet, role)
        with entry.lock:
            sm = entry.sm
            if sm.state == ProtocolState.BOTH_COMMITTED:
                sm.transition(ProtocolState.REVEAL_SENT)
                sm.transition(ProtocolState.STEP_VERIFIED)
                entry.reveal_sent_step = step
                logger.debug(
                    "[Coordinator] reveal_exchange_complete %s step=%d → STEP_VERIFIED",
                    game_id,
                    step,
                )
            elif sm.state == ProtocolState.REVEAL_RECEIVED:
                sm.transition(ProtocolState.STEP_VERIFIED)
                entry.reveal_sent_step = step
            elif sm.state == ProtocolState.STEP_VERIFIED:
                pass  # idempotent
