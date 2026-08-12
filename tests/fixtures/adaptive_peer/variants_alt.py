"""Compatible envelope variants: nested, packed, enum_aliases."""

from __future__ import annotations

import json

from .common import _fail_response, _is_probe, _ok_response


def register_nested(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_nested(
        header: dict | None = None,
        body: dict | None = None,
    ) -> dict:
        """Nested envelope action."""
        header = header or {}
        game_id = header.get("game_id", "")
        phase = header.get("phase", "")
        gamelet = header.get("gamelet", 0)
        if _is_probe(game_id):
            return _fail_response(nested=nested_response, game_id=game_id, phase=phase)
        return _ok_response(
            nested=nested_response,
            game_id=game_id,
            phase=phase,
            gamelet=gamelet,
            result={"winner": "cop"},
        )


def register_packed(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_packed(
        game_id: str = "",
        packed_message: str = "",
        signature: str = "",
        message_json: str = "",
        gamelet: int = 0,
    ) -> dict:
        """Packed JSON action."""
        actual_gid = game_id
        actual_phase = ""
        for msg_str in (packed_message, message_json):
            if not msg_str:
                continue
            try:
                parsed = json.loads(msg_str)
                if not actual_gid:
                    actual_gid = str(parsed.get("game_id", ""))
                if not actual_phase:
                    actual_phase = str(parsed.get("phase", ""))
            except (json.JSONDecodeError, TypeError):
                pass
        return respond(actual_gid, phase=actual_phase, gamelet=gamelet)


def register_enum_aliases(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_enum(
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
        """Enum alias action (NORTH/SOUTH/EAST/WEST)."""
        return respond(game_id, phase=phase, gamelet=gamelet)


ALT_VARIANTS = {
    "nested": register_nested,
    "packed": register_packed,
    "enum_aliases": register_enum_aliases,
}
