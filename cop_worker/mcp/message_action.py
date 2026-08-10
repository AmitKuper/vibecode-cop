"""ActionMessage: the per-phase wire message dataclass."""

import json
from dataclasses import dataclass


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
