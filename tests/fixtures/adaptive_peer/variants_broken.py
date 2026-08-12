"""INCOMPATIBLE variants (broken schemas), part 1."""

from __future__ import annotations


def register_nonce_in_reveal(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_nonce_reveal(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        phase: str = "",
        commitment: str = "",
        move: str = "",
        nonce: str = "",  # VIOLATION: nonce required in reveal
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
    ) -> dict:
        """INCOMPATIBLE: requires nonce during reveal."""
        return respond(game_id, phase=phase)


def register_missing_commitment(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_no_commit(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        move: str = "",  # No commitment field
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
    ) -> dict:
        """INCOMPATIBLE: no commitment field."""
        return respond(game_id)


def register_missing_final_result(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_no_audit(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        phase: str = "",
        commitment: str = "",
        move: str = "",
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
    ) -> dict:
        """INCOMPATIBLE: missing final_audit support."""
        # Server responds but schema omits nonces field (final_audit cannot work)
        return respond(game_id, phase=phase)


def register_mutable_canonicalization(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_float_step(
        game_id: str = "",
        step: float = 0.0,  # VIOLATION: float step
        role: str = "",
        phase: str = "",
        commitment: str = "",
        move: str = "",
        nonces: dict | None = None,
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
    ) -> dict:
        """INCOMPATIBLE: float step type."""
        return respond(game_id, phase=phase)


def register_phase_order(mcp, respond, nested_response: bool) -> None:
    @mcp.tool(name="action")
    def action_wrong_order(
        game_id: str = "",
        step: int = 0,
        role: str = "",
        move: str = "",  # reveal comes first (no commitment)
        commitment: str = "",
        config_sha256: str = "",
        signature: str = "",
        gamelet: int = 0,
    ) -> dict:
        """INCOMPATIBLE: phase ordering violated (reveal before commit)."""
        return respond(game_id)


BROKEN_VARIANTS = {
    "nonce_in_reveal": register_nonce_in_reveal,
    "missing_commitment": register_missing_commitment,
    "missing_final_result": register_missing_final_result,
    "mutable_canonicalization": register_mutable_canonicalization,
    "phase_order": register_phase_order,
}
