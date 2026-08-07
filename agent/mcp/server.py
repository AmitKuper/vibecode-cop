"""FastMCP server for agent orchestrator — delegates to crewAI agents.

Tool registration is split into:
  server_tools_game — start_game, action
  server_tools_info — ping, get_config, get_protocol
"""

import logging
from collections.abc import Callable
from pathlib import Path

from fastmcp import FastMCP

from agent.adaptive.reference_v3 import ReferenceV3Session, register_reference_v3_tools
from agent.mcp.log import GameLog
from agent.mcp.server_tools_game import register_game_tools
from agent.mcp.server_tools_info import register_info_tools

logger = logging.getLogger(__name__)


class AgentMCPServer:
    """FastMCP server for agent-based game orchestrator.

    Receives MCP messages from opponent and delegates to crewAI agents.
    """

    def __init__(
        self,
        role: str,
        secret: str,
        config_sha256: str,
        games_dir: Path = Path("./games"),
        handler_callbacks: dict[str, Callable] | None = None,
    ):
        self.role = role
        self.secret = secret
        self.config_sha256 = config_sha256
        if secret == "dev-secret-change-me":
            logger.warning(
                "SECURITY: shared secret is the default dev value. "
                "Set crypto.shared_secret in config or GAME_SECRET env var before deployment."
            )
        self.games_dir = Path(games_dir)
        self.games_dir.mkdir(parents=True, exist_ok=True)
        self.handler_callbacks = handler_callbacks or {}
        self.game_logs: dict[str, GameLog] = {}
        self.mcp = FastMCP(
            name=f"Agent-{role.capitalize()}",
            instructions=f"{role.capitalize()} agent with crewAI orchestration",
        )

        async def _outbound_not_configured(_tool_name: str, _params: dict) -> dict:
            raise RuntimeError("reference-v3 outbound transport is not configured on the server")

        # The handlers are deliberately queue-only.  A separately running game loop owns
        # outbound calls, so two push-style peers can never block inside each other's MCP tool.
        self.reference_v3_session = ReferenceV3Session(_outbound_not_configured)
        self._register_tools()

    def _register_tools(self) -> None:
        register_game_tools(
            self.mcp,
            self.role,
            self.secret,
            self.config_sha256,
            self.games_dir,
            self.game_logs,
            self.handler_callbacks,
        )
        register_info_tools(self.mcp, self.role, self.config_sha256)
        register_reference_v3_tools(self.mcp, self.reference_v3_session)

    def get_game_log(self, game_id: str) -> GameLog | None:
        return self.game_logs.get(game_id)

    async def run_async(self, host: str = "localhost", port: int = 5000) -> None:
        logger.info(f"Starting Agent MCP server on {host}:{port}")
        await self.mcp.run_async(transport="http", host=host, port=port)
