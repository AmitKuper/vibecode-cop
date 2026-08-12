"""Compatible tool-surface variants: native, split, renamed."""

from __future__ import annotations


def register_native(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        phase: str = "",
        commitment: str = "",
        move: str = "",
        nonces: dict | None = None,
        config_sha256: str = "",
        timestamp: str = "",
        reason: str = "",
        result_hash: str = "",
        signed_agreement: dict | None = None,
        signed_audit_summary: dict | None = None,
        signature: str = "",
        gamelet: int = 0,
        message_json: str = "",
    ) -> dict:
        """Canonical single action tool."""
        return respond(game_id, phase=phase, gamelet=gamelet)


def register_split(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="commit_move")
    def commit_move(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        commitment: str = "",
        hint: str = "",
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
    ) -> dict:
        """Commit to a move."""
        return respond(game_id, phase="commit", gamelet=gamelet)

    @mcp.tool(name="reveal_move")
    def reveal_move(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        move: str = "",
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
    ) -> dict:
        """Reveal committed move."""
        return respond(game_id, phase="reveal", gamelet=gamelet)

    @mcp.tool(name="action")
    def action_split(
        game_id: str = "",
        phase: str = "",
        role: str = "",
        nonces: dict | None = None,
        config_sha256: str = "",
        result_hash: str = "",
        signed_agreement: dict | None = None,
        signed_audit_summary: dict | None = None,
        reason: str = "",
        signature: str = "",
        gamelet: int = 0,
        message_json: str = "",
    ) -> dict:
        """Start/audit/result."""
        return respond(game_id, phase=phase, gamelet=gamelet)


def register_renamed(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="game_move")
    def game_move(
        game_id: str = "",
        step_num: int = 0,
        player_role: str = "",
        action_phase: str = "",
        move_commitment: str = "",
        action: str = "",
        audit_nonces: dict | None = None,
        config_hash: str = "",
        ts: str = "",
        signature: str = "",
        gamelet: int = 0,
        message_json: str = "",
        reason: str = "",
        result_hash: str = "",
        signed_agreement: dict | None = None,
        signed_audit_summary: dict | None = None,
    ) -> dict:
        """Renamed game move tool."""
        return respond(game_id, phase=action_phase, gamelet=gamelet)


CORE_VARIANTS = {
    "native": register_native,
    "split": register_split,
    "renamed": register_renamed,
}
