"""MCP tool registration — ping, get_config, get_protocol tools."""

from __future__ import annotations

_PROTOCOL_FIELDS = {
    "game_id":       "game_id",
    "gamelet":       "gamelet",
    "step":          "step",
    "role":          "role",
    "phase":         "phase",
    "config_sha256": "config_sha256",
    "state_hash":    "state_hash",
    "h_commit":      "h_commit",
    "h_commit_ack":  "h_commit_ack",
    "move":          "move",
    "hint":          "hint",
    "intent":        "intent",
    "nonce":         "nonce",
    "nonces":        "nonces",
    "timestamp":     "timestamp",
}


def register_info_tools(mcp, role: str, config_sha256: str) -> None:
    """Register ping, get_config, get_protocol MCP tools onto mcp instance."""

    @mcp.tool()
    def ping() -> dict:
        """Health check — confirms the agent is running and ready.

        Call this before start_game to verify the agent is reachable.

        Returns:
            {"ok": true, "role": str}
        """
        return {"ok": True, "role": role}

    @mcp.tool()
    def get_config() -> dict:
        """Return this agent's agreed config hash and protocol version.

        Remote agents call this before start_game to confirm both sides
        loaded the same game_config (identified by its SHA-256 hash).
        The shared secret is NOT included in this response.

        Returns:
            {"config_sha256": str, "protocol_version": str, "role": str}
        """
        return {"config_sha256": config_sha256, "protocol_version": "1.0", "role": role}

    @mcp.tool()
    def get_protocol() -> dict:
        """Return the full protocol definition for this agent.

        Remote agents call this during MCP discovery to learn the exact
        field names used inside game message payloads, signing scheme, and
        payload encoding — so they can translate their internal representation
        to the format this agent expects.

        Returns:
            {
              "protocol": "cop-thief-commit-reveal",
              "version": "1.0",
              "signing": {"required": bool, "algorithm": str, ...},
              "payload_encoding": "json_string" | "object",
              "fields": {<concept>: <field_name>, ...}
            }
        """
        return {
            "protocol": "cop-thief-commit-reveal",
            "version": "1.0",
            "signing": {
                "required": True,
                "algorithm": "hmac-sha256",
                "encoding": "hex",
                "canonical_json": True,
            },
            "payload_encoding": "json_string",
            "fields": _PROTOCOL_FIELDS,
        }
