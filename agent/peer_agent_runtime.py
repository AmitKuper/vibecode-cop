"""PeerAgentRuntime — production P2P runtime: MCP server + PeerRuntime.

Replaces the standalone GameOrchestrator in production entrypoints.
  PeerAgentRuntime = MCP server + PeerRuntime + strategy + report manager

Passive helpers (thief commit/reveal) are in peer_agent_passive.py.
"""

import asyncio
import logging
from pathlib import Path

from agent.mcp.server import AgentMCPServer
from agent.peer_agent_passive import (
    handle_passive_commit,
    handle_passive_reveal,
    init_passive_game,
)
from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)


class PeerAgentRuntime:
    """Production agent runtime: wraps AgentMCPServer + PeerRuntime.

    Cop (role="cop"): active mode — PeerRuntime.run_game() is launched as a
    background asyncio task when start_game is received from the thief.

    Thief (role="thief"): passive mode — handles commit/reveal calls inline
    as the cop drives each turn; sends final_audit at game end.
    """

    def __init__(
        self,
        role: str,
        secret: str,
        config_sha256: str,
        opponent_url: str,
        games_dir: Path,
        group_name: str = "unknown",
        llm_dict: dict | None = None,
    ):
        if role not in ("cop", "thief"):
            raise ValueError(f"role must be 'cop' or 'thief', got {role!r}")
        self.role = role
        self._llm_dict = llm_dict
        self._peer_runtime = PeerRuntime(
            role=role, secret=secret, config_sha256=config_sha256,
            opponent_url=opponent_url, games_dir=Path(games_dir), group_name=group_name,
        )
        self._rules_ref: list = []  # mutable cell so passive helpers can update it
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mcp_server = AgentMCPServer(
            role=role, secret=secret, config_sha256=config_sha256,
            games_dir=Path(games_dir),
            handler_callbacks={
                "on_start_game": self._on_start_game,
                "on_action": self._on_action,
            },
        )
        logger.info(f"PeerAgentRuntime initialised for {role}")

    def _on_start_game(self, message) -> dict:
        game_id = message.game_id
        if self.role == "cop":
            loop = self._loop
            if loop is None or not loop.is_running():
                logger.error("[PeerAgentRuntime/cop] No running event loop — cannot start game")
                return {"ok": False, "error": "No event loop", "game_id": game_id}
            asyncio.run_coroutine_threadsafe(self._peer_runtime.run_game(game_id), loop)
            logger.info(f"[PeerAgentRuntime/cop] Scheduled PeerRuntime.run_game({game_id})")
        else:
            init_passive_game(self._peer_runtime, game_id, self._rules_ref)
        return {"ok": True, "game_id": game_id}

    def _on_action(self, game_id: str, message) -> dict:
        phase = message.phase
        if phase == "commit":
            return handle_passive_commit(self._peer_runtime, game_id, message, self._rules_ref)
        if phase == "reveal":
            return handle_passive_reveal(self._peer_runtime, game_id, message, self._rules_ref)
        if phase == "final_audit":
            nonces = {str(s): p["nonce"] for s, p in self._peer_runtime._my_commits.items()}
            return {"ok": True, "phase": "final_audit", "nonces": nonces}
        if phase == "game_end":
            return {"ok": True, "phase": "game_end"}
        return {"ok": False, "error": f"Unknown phase: {phase}"}

    async def run_async(self, host: str = "0.0.0.0", port: int = 5000) -> None:
        """Start the MCP server. Cop's PeerRuntime loop starts on first start_game call."""
        self._loop = asyncio.get_running_loop()
        logger.info(f"[PeerAgentRuntime/{self.role}] Starting MCP server on {host}:{port}")
        await self._mcp_server.run_async(host=host, port=port)
