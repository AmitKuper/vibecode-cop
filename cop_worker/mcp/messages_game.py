"""Game-specific message types: StartGameMessage and ActionMessage."""

import json
from dataclasses import dataclass


@dataclass
class StartGameMessage:
    """Handshake message for game initialization.

    Fields:
        game_id: Unique game identifier
        roles: Dict mapping role -> peer name (e.g. {"cop": "player1", "police": "player2"})
        config_sha256: SHA-256 hash of agreed config (binds scent model, board size, etc)
        protocol_version: "1.0"
        endpoint: This peer's MCP endpoint (http://localhost:5000/mcp)
        timestamp: ISO 8601 timestamp
    """

    game_id: str
    roles: dict  # {"cop": name, "police": name}
    config_sha256: str
    protocol_version: str
    endpoint: str
    timestamp: str
    peer_url: str | None = None  # URL of the OTHER player (not the initiator)
    signed_declaration: dict | None = None

    _KNOWN_FIELDS = frozenset(
        {
            "game_id",
            "roles",
            "config_sha256",
            "protocol_version",
            "endpoint",
            "timestamp",
            "peer_url",
            "signed_declaration",
        }
    )

    @staticmethod
    def from_json(json_str: str) -> "StartGameMessage":
        """Parse from JSON string, ignoring unknown fields for forward compatibility."""
        try:
            obj = json.loads(json_str)
            filtered = {k: v for k, v in obj.items() if k in StartGameMessage._KNOWN_FIELDS}
            return StartGameMessage(**filtered)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            raise ValueError(f"Invalid StartGameMessage JSON: {e}") from e

    def to_dict(self) -> dict:
        """Convert to dict for signing/sending."""
        d = {
            "game_id": self.game_id,
            "roles": self.roles,
            "config_sha256": self.config_sha256,
            "protocol_version": self.protocol_version,
            "endpoint": self.endpoint,
            "timestamp": self.timestamp,
        }
        if self.peer_url is not None:
            d["peer_url"] = self.peer_url
        if self.signed_declaration is not None:
            d["signed_declaration"] = self.signed_declaration
        return d


@dataclass
class ActionMessage:
    """Action message for all game protocol phases (commit/ack/reveal/final_audit/abort)."""

    game_id: str
    step: int
    role: str  # "cop", "police", or "initiator"
    config_sha256: str
    timestamp: str
    phase: str  # from MessagePhase
    h_commit: str | None = None
    h_commit_ack: str | None = None
    move: str | None = None
    hint: str | None = None
    intent: str | None = None
    state_hash: str | None = None
    nonces: dict | None = None  # for final_audit
    game_log: list | None = None  # optional full game log
    reason: str | None = None  # for abort / game_end
    board_state: dict | None = None  # current board state (sent in commit requests)
    signed_audit_summary: dict | None = None
    signed_result_agreement: dict | None = None
    signed_audit_summaries: list | None = None

    @staticmethod
    def from_json(json_str: str) -> "ActionMessage":
        """Parse from JSON string."""
        try:
            obj = json.loads(json_str)
            known = {
                "game_id",
                "step",
                "role",
                "config_sha256",
                "timestamp",
                "phase",
                "h_commit",
                "h_commit_ack",
                "move",
                "hint",
                "intent",
                "state_hash",
                "nonces",
                "game_log",
                "reason",
                "board_state",
                "signed_audit_summary",
                "signed_result_agreement",
                "signed_audit_summaries",
            }
            filtered = {k: v for k, v in obj.items() if k in known}
            return ActionMessage(**filtered)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            raise ValueError(f"Invalid ActionMessage JSON: {e}") from e

    def to_dict(self) -> dict:
        """Convert to dict for signing/sending."""
        result = {
            "game_id": self.game_id,
            "step": self.step,
            "role": self.role,
            "config_sha256": self.config_sha256,
            "timestamp": self.timestamp,
            "phase": self.phase,
        }

        # Only include fields that are set
        if self.h_commit is not None:
            result["h_commit"] = self.h_commit
        if self.h_commit_ack is not None:
            result["h_commit_ack"] = self.h_commit_ack
        if self.move is not None:
            result["move"] = self.move
        if self.hint is not None:
            result["hint"] = self.hint
        if self.intent is not None:
            result["intent"] = self.intent
        if self.state_hash is not None:
            result["state_hash"] = self.state_hash
        if self.nonces is not None:
            result["nonces"] = self.nonces
        if self.game_log is not None:
            result["game_log"] = self.game_log
        if self.reason is not None:
            result["reason"] = self.reason
        if self.board_state is not None:
            result["board_state"] = self.board_state
        if self.signed_audit_summary is not None:
            result["signed_audit_summary"] = self.signed_audit_summary
        if self.signed_result_agreement is not None:
            result["signed_result_agreement"] = self.signed_result_agreement
        if self.signed_audit_summaries is not None:
            result["signed_audit_summaries"] = self.signed_audit_summaries

        return result
