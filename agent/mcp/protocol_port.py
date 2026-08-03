"""Game protocol port — deterministic mapping from game actions to transport calls."""
import hashlib
import json

from agent.mcp.transport_port import TransportPort

# Deterministic phase-to-tool mapping (locked in Step-0)
DEFAULT_TOOL_MAP = {
    "start_game": "start_game",
    "commit": "action",
    "reveal": "action",
    "final_audit": "action",
    "audit_summary": "action",
    "result_agreement": "action",
    "game_end": "action",
    "abort": "action",
}


class ProtocolMapping:
    """Locked protocol mapping — negotiated in Step-0, then deterministic."""

    def __init__(self, tool_map: dict[str, str]):
        self._map = tool_map
        self._locked = False
        self._hash: str | None = None

    def lock(self) -> str:
        """Lock the mapping and return its hash."""
        canonical = json.dumps(self._map, sort_keys=True, separators=(",", ":")).encode()
        self._hash = hashlib.sha256(canonical).hexdigest()
        self._locked = True
        return self._hash

    def tool_for(self, phase: str) -> str:
        if not self._locked:
            raise RuntimeError("Protocol mapping must be locked before use (Step-0 incomplete)")
        if phase not in self._map:
            raise KeyError(f"Unknown protocol phase: {phase!r}")
        return self._map[phase]

    @property
    def mapping_hash(self) -> str | None:
        return self._hash

    @property
    def is_locked(self) -> bool:
        return self._locked

    @classmethod
    def default(cls) -> "ProtocolMapping":
        return cls(DEFAULT_TOOL_MAP)


class GameProtocolPort:
    """Deterministic game-to-transport bridge. No per-turn LLM calls."""

    def __init__(self, transport: TransportPort, mapping: ProtocolMapping):
        self._transport = transport
        self._mapping = mapping

    async def start_game(self, params: dict) -> dict:
        return await self._transport.send(self._mapping.tool_for("start_game"), params)

    async def commit(self, params: dict) -> dict:
        return await self._transport.send(
            self._mapping.tool_for("commit"), {"phase": "commit", **params}
        )

    async def reveal(self, params: dict) -> dict:
        return await self._transport.send(
            self._mapping.tool_for("reveal"), {"phase": "reveal", **params}
        )

    async def final_audit(self, params: dict) -> dict:
        return await self._transport.send(
            self._mapping.tool_for("final_audit"), {"phase": "final_audit", **params}
        )

    async def audit_summary(self, params: dict) -> dict:
        return await self._transport.send(
            self._mapping.tool_for("audit_summary"), {"phase": "audit_summary", **params}
        )

    async def result_agreement(self, params: dict) -> dict:
        return await self._transport.send(
            self._mapping.tool_for("result_agreement"), {"phase": "result_agreement", **params}
        )

    async def game_end(self, params: dict) -> dict:
        return await self._transport.send(
            self._mapping.tool_for("game_end"), {"phase": "game_end", **params}
        )

    async def abort(self, params: dict) -> dict:
        return await self._transport.send(
            self._mapping.tool_for("abort"), {"phase": "abort", **params}
        )
