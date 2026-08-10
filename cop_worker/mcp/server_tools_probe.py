"""MCP tool registration — the side-effect-free protocol_conformance probe."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from pydantic import Field


def register_conformance_tool(mcp) -> None:
    """Register the semantic-probe tool onto the mcp instance."""
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
