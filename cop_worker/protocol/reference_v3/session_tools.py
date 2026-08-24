"""FastMCP tool registration for the reference-v3 session (split, 150-line rule)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - annotation only, avoids a circular import
    from cop_worker.protocol.reference_v3.session import ReferenceV3Session


def register_reference_v3_tools(mcp, session: ReferenceV3Session) -> None:
    """Expose the exact non-blocking FastMCP surface used by the unmodified league kit.

    Every tool sits behind an :class:`InboundGuard` (rule 29): a flooding peer
    gets a structured refusal, never a session-state mutation or a crash.
    """
    import logging as _logging

    from cop_worker.protocol.reference_v3.inbound_guard import InboundGuard

    _log = _logging.getLogger(__name__)
    _guard = InboundGuard()

    def _flooded(tool: str) -> dict:
        _log.warning("INBOUND GUARD refused %s (%d refusals so far)", tool, _guard.refused)
        return {"ok": False, "error": "rate_limited", "tool": tool}

    @mcp.tool
    def negotiate(message: dict) -> dict:
        """Receive the opponent's signed game agreement.

        Reply-greeting dialect (cosmos77 pairing, 2026-08-22): when our own
        greeting for the requested sub_game is already staged, the ack
        carries it as ``message`` — a strict superset of the bare ack, so
        push-dialect peers are unaffected while reply-dialect peers complete
        Step-0 from any single overlap instead of racing push cadences
        against handshake budgets.
        """
        if not _guard.allow():
            return _flooded("negotiate")
        _log.info(
            "TOOL_CALLED negotiate keys=%s",
            list(message.keys()) if isinstance(message, dict) else type(message),
        )
        session.receive_negotiation(message)
        reply: dict = {"ok": True}
        try:
            sg = int(message.get("sub_game_number", 0)) if isinstance(message, dict) else 0
            staged = getattr(session, "staged_greetings", {}).get(sg)
            if staged is not None:
                reply["message"] = staged
        except (TypeError, ValueError):
            pass
        return reply

    @mcp.tool
    def receive_turn(message: dict) -> dict:
        """Receive the opponent's turn message."""
        if not _guard.allow():
            return _flooded("receive_turn")
        _log.info(
            "TOOL_CALLED receive_turn keys=%s",
            list(message.keys()) if isinstance(message, dict) else type(message),
        )
        session.receive_turn(message)
        return {"ok": True}

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        """Receive the opponent's end-of-game audit reveal (records + nonces)."""
        if not _guard.allow():
            return _flooded("submit_audit")
        _log.info(
            "TOOL_CALLED submit_audit keys=%s",
            list(payload.keys()) if isinstance(payload, dict) else type(payload),
        )
        session.receive_audit(payload)
        return {"ok": True}

    @mcp.tool
    def receive_control(message: dict) -> dict:
        """Receive an opponent control signal (enable / status / restart / quit)."""
        if not _guard.allow():
            return _flooded("receive_control")
        _log.info(
            "TOOL_CALLED receive_control session_id=%s controls_before=%d keys=%s",
            id(session),
            len(session.controls),
            list(message.keys()) if isinstance(message, dict) else type(message),
        )
        session.receive_control(message)
        _log.info("receive_control DONE controls_after=%d", len(session.controls))
        return {"ok": True}
