"""ObservationProcessor — normalises raw peer event payloads into domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OpponentTurn:
    """Normalised opponent turn event."""

    step: int
    kind: str  # "commit" | "reveal" | "ack"
    commitment_hash: str | None = None
    nonce: str | None = None
    action: dict | None = None
    # Opponent's transmitted scent field ({'r,c': intensity}) and free-language hint.
    # Preserved so the worker can feed opponent_scent + last_hint into the RL observation
    # (mirrors the reference-v3 wire, which carries smell_grid/hint on every turn).
    smell_grid: dict | None = None
    hint: str | None = None


@dataclass
class AuditSubmission:
    """Normalised opponent audit bundle."""

    game_uid: str
    sub_game_number: int
    role: str
    steps: list[dict]
    terminal_condition: str
    final_step: int
    log_hash: str


@dataclass
class ControlMessage:
    """Normalised control signal from peer or LM."""

    kind: str  # "timeout" | "abort" | "ping"
    reason: str | None = None


class ObservationProcessorError(Exception):
    """Raised when a payload cannot be normalised."""


class ObservationProcessor:
    """Converts raw MCP dict payloads into typed domain objects.

    Called by the worker before processing any inbound event. All validation
    of payload shape happens here; downstream code receives typed objects only.
    """

    def normalise_turn(self, payload: dict[str, Any]) -> OpponentTurn:
        """Convert a raw receive_turn payload to an OpponentTurn.

        Args:
            payload: Raw MCP dict from deliver_event with event_type='opponent_turn'.

        Returns:
            OpponentTurn with typed fields.

        Raises:
            ObservationProcessorError: If required fields are missing or invalid.
        """
        kind = payload.get("kind")
        if kind not in ("commit", "reveal", "ack"):
            raise ObservationProcessorError(f"Unknown turn kind: {kind!r}")
        step = payload.get("step")
        if not isinstance(step, int):
            raise ObservationProcessorError(f"step must be int, got {type(step)}")
        return OpponentTurn(
            step=step,
            kind=kind,
            commitment_hash=payload.get("commitment_hash"),
            nonce=payload.get("nonce"),
            action=payload.get("action"),
            smell_grid=payload.get("smell_grid"),
            hint=payload.get("hint"),
        )

    def normalise_audit(self, payload: dict[str, Any]) -> AuditSubmission:
        """Convert a raw submit_audit payload to an AuditSubmission.

        Args:
            payload: Raw MCP dict from deliver_event with event_type='opponent_audit'.

        Returns:
            AuditSubmission with typed fields.

        Raises:
            ObservationProcessorError: If required fields are missing.
        """
        required = (
            "game_uid",
            "sub_game_number",
            "role",
            "steps",
            "terminal_condition",
            "final_step",
            "log_hash",
        )
        for field in required:
            if field not in payload:
                raise ObservationProcessorError(f"Audit missing required field: {field}")
        return AuditSubmission(
            game_uid=payload["game_uid"],
            sub_game_number=payload["sub_game_number"],
            role=payload["role"],
            steps=payload["steps"],
            terminal_condition=payload["terminal_condition"],
            final_step=payload["final_step"],
            log_hash=payload["log_hash"],
        )

    def normalise_control(self, payload: dict[str, Any]) -> ControlMessage:
        """Convert a raw control payload to a ControlMessage.

        Args:
            payload: Raw MCP dict from deliver_event with event_type='control_signal'.

        Returns:
            ControlMessage with typed fields.

        Raises:
            ObservationProcessorError: If kind field is missing.
        """
        kind = payload.get("kind")
        if not kind:
            raise ObservationProcessorError("control_signal missing 'kind' field")
        return ControlMessage(kind=kind, reason=payload.get("reason"))
