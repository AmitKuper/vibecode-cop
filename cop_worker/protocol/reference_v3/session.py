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


from cop_worker.protocol.reference_v3.session_tools import (  # noqa: E402,F401
    register_reference_v3_tools,
)
