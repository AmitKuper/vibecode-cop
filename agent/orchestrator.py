"""crewAI-based orchestrator for game coordination via MCP."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crewai import Crew

from agent.llm import LLMConfig, LLMFactory
from agent.mcp.client import GameMCPClient
from agent.mcp.discovery import ProtocolDiscovery
from agent.mcp.server import AgentMCPServer
from agent.orchestrator_audit import AuditMixin
from agent.orchestrator_crew import CrewMixin
from agent.orchestrator_discovery import DiscoveryMixin
from agent.orchestrator_game import GameStateMixin
from agent.orchestrator_phase import PhaseMixin

logger = logging.getLogger(__name__)


class GameOrchestrator(GameStateMixin, CrewMixin, DiscoveryMixin, PhaseMixin, AuditMixin):
    """Coordinates crewAI agents with MCP message flow for game orchestration.

    Responsibilities:
    - Manages crewAI agents and crews per game_id
    - Loads/saves game state from dedicated memory folders
    - Delegates MCP messages to appropriate agents
    - Handles commitment-reveal protocol
    - Persists game state and events
    """

    def __init__(
        self,
        role: str,
        secret: str,
        config_sha256: str,
        games_dir: Path = Path("agent/memory"),
        opponent_url: str = "http://localhost:5001/mcp",
        local_url: str = "http://localhost:5000/mcp",
        llm_config: LLMConfig | None = None,
        llm_dict: dict | None = None,
        group_name: str = "unknown",
    ):
        """Initialize orchestrator.

        Args:
            role: "cop" or "thief"
            secret: Shared secret for HMAC signing
            config_sha256: SHA-256 of agreed config
            games_dir: Base directory for game memory (agent/memory)
            opponent_url: MCP URL of opponent
            local_url: This agent's MCP URL
            llm_config: Optional LLMConfig instance
            llm_dict: Optional dict with LLM config (provider, model, etc.)
            group_name: Group identifier for reports
        """
        self.role = role
        self.secret = secret
        self.config_sha256 = config_sha256
        self.group_id = group_name
        self.games_dir = Path(games_dir)
        self.games_dir.mkdir(parents=True, exist_ok=True)

        self.llm = self._initialize_llm(llm_config, llm_dict)

        self.mcp_server = AgentMCPServer(
            role=role,
            secret=secret,
            config_sha256=config_sha256,
            games_dir=self.games_dir,
            handler_callbacks={
                "on_start_game": self._on_start_game,
                "on_action": self._on_action,
            },
        )
        # peer_url is the base URL (no /mcp suffix) used by the discovery crew
        self.peer_url = opponent_url.rstrip("/").replace("/mcp", "")
        self.mcp_client = GameMCPClient(opponent_url, secret)
        self.protocol_discovery = ProtocolDiscovery(opponent_url)
        self.protocol_model: dict = {}
        self.mcp_skill = None  # set by discover_protocol after game start
        self.crews: dict[str, Crew] = {}

        logger.info(f"GameOrchestrator initialized for {role}")
        logger.info(f"LLM initialized: {self.llm}")

    def _initialize_llm(self, llm_config: LLMConfig | None, llm_dict: dict | None):
        """Initialize LLM from config or environment."""
        try:
            if llm_config:
                logger.info(
                    f"Using provided LLM config: {llm_config.provider.value}/{llm_config.model}"
                )
                return LLMFactory.create_llm(llm_config)
            elif llm_dict:
                logger.info("Creating LLM from dict config")
                return LLMFactory.create_from_dict(llm_dict)
            else:
                logger.info("Initializing LLM from environment variables")
                return LLMFactory.create_from_env()
        except Exception as e:
            logger.warning(f"Failed to initialize LLM: {e}, using crewAI default")
            logger.info("Set LLM_PROVIDER, LLM_MODEL, and relevant API keys to use custom LLM")
            return None

    async def run_async(self, host: str = "localhost", port: int = 5000) -> None:
        """Run MCP server. Discovery runs automatically on the first start_game call."""
        logger.info(f"Starting MCP server on {host}:{port}")
        await self.mcp_server.run_async(host=host, port=port)
