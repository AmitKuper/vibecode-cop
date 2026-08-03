"""Deterministic fixture opponents for protocol conformance tests."""

import hashlib
import json


class FixtureOpponent:
    """In-process deterministic opponent for conformance testing."""

    def __init__(self, role: str, grid_size: int = 7, move_sequence: list[str] | None = None):
        self._role = role
        self._grid_size = grid_size
        self._moves = move_sequence or ["N", "S", "E", "W", "STAY"] * 20
        self._step = 0
        self._nonces: dict[int, str] = {}

    def _make_nonce(self, step: int) -> str:
        return hashlib.sha256(f"fixture-nonce-{step}".encode()).hexdigest()[:16]

    def _make_h_commit(self, move: str, nonce: str) -> str:
        payload = json.dumps({"move": move, "nonce": nonce}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    async def handle(self, tool_name: str, params: dict) -> dict:
        """Handle a protocol request deterministically."""
        phase = params.get("phase", tool_name)

        if tool_name == "start_game" or phase == "start_game":
            return {"status": "ok", "role": self._role, "ready": True}

        if phase == "commit":
            step = self._step
            move = self._moves[step % len(self._moves)]
            nonce = self._make_nonce(step)
            self._nonces[step] = nonce
            h_commit = self._make_h_commit(move, nonce)
            self._step += 1
            return {"status": "ok", "h_commit": h_commit, "step": step}

        if phase == "reveal":
            step = params.get("step", self._step - 1)
            move = self._moves[step % len(self._moves)]
            nonce = self._nonces.get(step, self._make_nonce(step))
            return {"status": "ok", "move": move, "hint": f"Going {move.lower()}", "nonce": nonce}

        if phase in ("final_audit", "audit_summary", "result_agreement", "game_end", "abort"):
            return {"status": "ok"}

        return {"status": "ok"}


class IncompatibleFixture:
    """Fixture with incompatible canonicalization — must be rejected in Step-0."""

    async def handle(self, tool_name: str, params: dict) -> dict:
        # Claims different commitment semantics
        if tool_name == "start_game":
            return {"status": "ok", "commitment_semantics": "move_only"}
        return {"status": "ok"}
