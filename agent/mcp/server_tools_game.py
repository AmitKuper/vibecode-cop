"""MCP tool registration — start_game and action tools."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import Field

from agent.mcp.log import GameLog
from agent.mcp.server_handlers import handle_action, handle_start_game


def register_game_tools(
    mcp,
    role: str,
    secret: str,
    config_sha256: str,
    games_dir: Path,
    game_logs: dict[str, GameLog],
    handler_callbacks: dict[str, Callable],
) -> None:
    """Register start_game and action MCP tools onto mcp instance."""

    @mcp.tool()
    def start_game(
        message_json: Annotated[
            str,
            Field(
                description=(
                    "Canonical JSON string of the StartGameMessage payload. "
                    "Keys must be sorted, no extra whitespace. "
                    "Fields: game_id, roles, config_sha256, protocol_version, "
                    "endpoint, timestamp, peer_url. "
                    "The HMAC signature must be computed over this exact string."
                )
            ),
        ],
        signature: Annotated[
            str,
            Field(
                description=(
                    "HMAC-SHA256 hex digest (64 lowercase hex chars) of message_json, "
                    "keyed with the shared game secret."
                )
            ),
        ],
    ) -> dict:
        """Handshake to initialize a new game session between two agents.

        Call this once before any action() calls. The caller must supply a
        canonical JSON payload and its HMAC-SHA256 signature. The agent will
        run MCP discovery of the caller's peer_url, then return ok=true when
        ready to receive action() calls for this game_id.

        Returns:
            {"ok": true/false, "error": str, "game_id": str}
        """
        return handle_start_game(
            role,
            secret,
            config_sha256,
            games_dir,
            game_logs,
            handler_callbacks,
            message_json,
            signature,
        )

    @mcp.tool()
    def action(
        game_id: Annotated[
            str,
            Field(description="Unique identifier of the active game session."),
        ],
        message_json: Annotated[
            str,
            Field(
                description=(
                    "Canonical JSON string of the ActionMessage payload. "
                    "Keys must be sorted, no extra whitespace. "
                    "Common fields: game_id, step, role, phase, config_sha256, timestamp. "
                    "Phase-specific fields — "
                    "commit: state_hash, h_commit (SHA-256 of move+hint+intent+nonce); "
                    "reveal: move (N/S/E/W/STAY), hint (≤15 words), intent (truth|lie), "
                    "state_hash — nonce is withheld until final_audit; "
                    "final_audit: nonces (dict of step→nonce). "
                    "The HMAC signature must be computed over this exact string."
                )
            ),
        ],
        signature: Annotated[
            str,
            Field(description="HMAC-SHA256 hex digest of message_json."),
        ],
    ) -> dict:
        """Execute a game action for any protocol phase.

        Handles all phases of the commit-reveal protocol:
          commit      — agent receives a state snapshot and returns h_commit
          reveal      — agent reveals move, hint, intent, state_hash (nonce withheld)
          final_audit — agent returns all nonces for tamper verification
          game_end    — notify agent the game is over

        Returns:
            {"ok": true/false, "error": str, "phase": str}
        """
        return handle_action(
            role,
            secret,
            config_sha256,
            games_dir,
            game_logs,
            handler_callbacks,
            game_id,
            message_json,
            signature,
        )
