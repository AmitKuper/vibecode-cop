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


from cop_worker.mcp.message_action import ActionMessage  # noqa: E402,F401  (re-export)
