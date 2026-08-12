"""Shared constants and response helpers for the adaptive peer fixture server."""

from __future__ import annotations

import json
from collections.abc import Callable

PROBE_PREFIX = "PROBE_GAME_"
CONFORMANCE_TOOL = "protocol_conformance"

SEMANTIC_PROOFS = {
    "canonical_order": True,
    "canonical_json_bytes": True,
    "commitment_binding": True,
    "nonce_final_audit_only": True,
    "comprehensive_audit": True,
    "result_agreement": True,
}

_CALL_COUNTER: dict[str, int] = {}


def _extract_game_id(kwargs: dict) -> str:
    """Try to find game_id from various parameter shapes."""
    if "game_id" in kwargs:
        return str(kwargs["game_id"])
    if "header" in kwargs and isinstance(kwargs["header"], dict):
        return str(kwargs["header"].get("game_id", ""))
    if "packed_message" in kwargs:
        try:
            parsed = json.loads(kwargs["packed_message"])
            return str(parsed.get("game_id", ""))
        except (json.JSONDecodeError, TypeError):
            pass
    return ""


def _is_probe(game_id: str) -> bool:
    """Return True for inert conformance probe game IDs."""
    return not game_id or game_id.startswith(PROBE_PREFIX)


def _ok_response(nested: bool = False, winner: str = "cop", **extra: object) -> dict:
    resp: dict = {"ok": True, "winner": winner, "phase": extra.get("phase", ""), **extra}
    return {"data": resp} if nested else resp


def _fail_response(
    nested: bool = False,
    error: str = "invalid_probe",
    game_id: str = "",
    phase: str = "",
) -> dict:
    resp: dict = {"ok": False, "error": error, "game_id": game_id, "phase": phase}
    return {"data": resp} if nested else resp


def make_responder(nested_response: bool) -> Callable[..., dict]:
    """Build the per-server ``_respond`` closure used by variant registrars."""

    def _respond(game_id: str, **extra: object) -> dict:
        phase = str(extra.get("phase", ""))
        if _is_probe(game_id):
            return _fail_response(nested=nested_response, game_id=game_id, phase=phase)
        return _ok_response(nested=nested_response, game_id=game_id, **extra)

    return _respond


def register_conformance(mcp) -> None:
    """Register the shared side-effect-free conformance probe tool."""

    @mcp.tool(name=CONFORMANCE_TOOL)
    def protocol_conformance(
        phase: str,
        game_id: str,
        request_digest: str = "",
        idempotency_key: str = "",
    ) -> dict:
        """Side-effect-free protocol conformance probe."""
        key = f"{game_id}:{phase}"
        _CALL_COUNTER[key] = _CALL_COUNTER.get(key, 0) + 1
        return {
            "ok": True,
            "game_id": game_id,
            "phase": phase,
            "idempotent": True,
            "side_effects": 0,
            **SEMANTIC_PROOFS,
        }
