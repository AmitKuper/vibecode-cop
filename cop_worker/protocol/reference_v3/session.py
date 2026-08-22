"""Gameplay session state machine and MCP tool registration."""

from __future__ import annotations

from collections import deque

from cop_worker.protocol.reference_v3.constants import (
    ReferenceV3EquivocationError,
    ReferenceV3Error,
)
from cop_worker.protocol.reference_v3.turns import (
    ReferenceV3Inbox,
    validate_turn,
)


class ReferenceV3Session:
    """Non-blocking four-tool session used by a game loop after profile lock."""

    def __init__(self, tool_caller, *, reorder_window: int = 4) -> None:
        self._call = tool_caller
        self.turns = ReferenceV3Inbox(window=reorder_window)
        self.agreements: deque[dict] = deque()
        self.audits: deque[dict] = deque()
        self.controls: deque[dict] = deque()
        self.turn_messages: deque[dict] = deque()  # full wire-turn messages (for smell_grid access)
        self.sent_turns: list[dict] = []  # full OUTBOUND wire turns (game-record capture)
        self.local_records: list[dict] = []
        self._local_records_by_step: dict[int, dict] = {}
        self.per_turn_llm_calls = 0
        # Expected sender: "police" or "police". Turns from the wrong sender are silently
        # discarded. This prevents late-arriving turns from a previous sub-game (different
        # sender role) from polluting the inbox for the current sub-game.
        self.expected_turn_sender: str | None = None

    async def send_negotiation(self, message: dict) -> dict:
        return await self._call("negotiate", {"message": message})

    async def send_turn(self, turn: dict, private_record: dict) -> dict:
        validate_turn(turn)
        if turn["commit"] != private_record.get("commit"):
            raise ReferenceV3Error("wire turn and private audit record have different commits")
        # Durable callers persist before invoking this method.  Keep one local record before the
        # network call so an acknowledgement loss retries the same bytes idempotently.
        step = int(turn["step"])
        prior = self._local_records_by_step.get(step)
        if prior is not None and prior.get("commit") != turn["commit"]:
            raise ReferenceV3EquivocationError(f"different local commit retry for step {step}")
        if prior is None:
            stored = dict(private_record)
            self._local_records_by_step[step] = stored
            self.local_records.append(stored)
            # Keep the WIRE turn too (scent/hint/claims): the sealed record has only
            # the private payload, and the game-record artifact wants what we sent.
            self.sent_turns.append(dict(turn))
        return await self._call("receive_turn", {"message": turn})

    async def send_audit(self, sender: str, result_claim: str) -> dict:
        if result_claim not in {"capture", "survival", "timeout", "technical_loss"}:
            raise ReferenceV3Error("invalid reference-v3 result claim")
        payload = {"sender": sender, "records": self.local_records, "result_claim": result_claim}
        return await self._call("submit_audit", {"payload": payload})

    async def send_control(self, message: dict) -> dict:
        return await self._call("receive_control", {"message": message})

    def receive_turn(self, message: dict) -> list[dict]:
        if (
            self.expected_turn_sender is not None
            and isinstance(message, dict)
            and message.get("sender") != self.expected_turn_sender
        ):
            import logging as _lg

            _lg.getLogger(__name__).warning(
                "receive_turn: discarding turn from %r (expected %r)"
                " — late arrival from prev sub-game",
                message.get("sender"),
                self.expected_turn_sender,
            )
            return []
        self.turn_messages.append(dict(message))
        return self.turns.offer(message)

    def receive_negotiation(self, message: dict) -> None:
        self.agreements.append(dict(message))

    def receive_audit(self, payload: dict) -> None:
        self.audits.append(dict(payload))

    def receive_control(self, message: dict) -> None:
        self.controls.append(dict(message))


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
