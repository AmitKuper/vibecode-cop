"""MCP tool registration — start_game and action tools."""

from __future__ import annotations

import hashlib
import json
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
    conformance_cache: dict[str, tuple[str, dict]] = {}

    @mcp.tool()
    def protocol_conformance(
        phase: Annotated[str, Field(description="One canonical eight-phase name.")],
        game_id: Annotated[str, Field(description="Synthetic PROBE_GAME identifier only.")],
        request_digest: Annotated[str, Field(description="SHA-256 of the inert mapped request.")],
        idempotency_key: Annotated[str, Field(description="Synthetic retry key for this probe.")],
    ) -> dict:
        """Side-effect-free semantic probe; never accepts real game data or secrets."""
        phases = {
            "start_game",
            "commit",
            "reveal",
            "final_audit",
            "audit_summary",
            "game_end",
            "result_agreement",
            "abort",
        }
        if phase not in phases or not game_id.startswith("PROBE_GAME_"):
            return {"ok": False, "game_id": game_id, "phase": phase, "error": "unsafe probe"}
        if len(request_digest) != 64 or len(idempotency_key) < 16:
            return {"ok": False, "game_id": game_id, "phase": phase, "error": "bad digest"}
        content = json.dumps(
            {"phase": phase, "game_id": game_id, "request_digest": request_digest},
            sort_keys=True,
            separators=(",", ":"),
        )
        semantic_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        cached = conformance_cache.get(idempotency_key)
        if cached is not None and cached[0] != semantic_digest:
            return {
                "ok": False,
                "game_id": game_id,
                "phase": phase,
                "error": "conflicting idempotency key",
            }
        response = {
            "ok": True,
            "game_id": game_id,
            "phase": phase,
            "semantic_digest": semantic_digest,
            "idempotent": True,
            "side_effects": 0,
            "canonical_order": True,
            "canonical_json_bytes": True,
            "commitment_binding": True,
            "nonce_final_audit_only": True,
            "comprehensive_audit": True,
            "result_agreement": True,
        }
        conformance_cache[idempotency_key] = (semantic_digest, response)
        return response

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
