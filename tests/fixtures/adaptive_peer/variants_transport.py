"""Compatible variants: optional_extra, nested_response, streamable_http/sse."""

from __future__ import annotations


def register_optional_extra(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_extra(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        phase: str = "",
        commitment: str = "",
        move: str = "",
        nonces: dict | None = None,
        config_sha256: str = "",
        client_version: str = "",
        trace_id: str = "",
        signature: str = "",
        gamelet: int = 0,
        message_json: str = "",
        reason: str = "",
        result_hash: str = "",
        signed_agreement: dict | None = None,
        signed_audit_summary: dict | None = None,
    ) -> dict:
        """Action with extra optional fields."""
        return respond(game_id, phase=phase, gamelet=gamelet)


def register_nested_response(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_nested_resp(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        phase: str = "",
        commitment: str = "",
        move: str = "",
        nonces: dict | None = None,
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
        message_json: str = "",
        reason: str = "",
        result_hash: str = "",
        signed_agreement: dict | None = None,
        signed_audit_summary: dict | None = None,
    ) -> dict:
        """Nested response action."""
        return respond(game_id, phase=phase, gamelet=gamelet)


def register_http_sse(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_http_sse(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        phase: str = "",
        commitment: str = "",
        move: str = "",
        nonces: dict | None = None,
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
        message_json: str = "",
        reason: str = "",
        result_hash: str = "",
        signed_agreement: dict | None = None,
        signed_audit_summary: dict | None = None,
    ) -> dict:
        """Standard action over HTTP or SSE transport."""
        return respond(game_id, phase=phase, gamelet=gamelet)


TRANSPORT_VARIANTS = {
    "optional_extra": register_optional_extra,
    "nested_response": register_nested_response,
    "streamable_http": register_http_sse,
    "sse": register_http_sse,
}
