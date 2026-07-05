"""FastMCP server for agent orchestrator - receives messages and delegates to crewAI agents."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from agent.mcp.log import GameLog
from agent.mcp.server_handlers import handle_action, handle_start_game

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
        """Initialize MCP server.

        Args:
            role: "cop" or "thief"
            secret: Shared secret for HMAC (from config)
            config_sha256: SHA-256 of agreed config
            games_dir: Directory to store game logs
            handler_callbacks: Dict of {handler_name: async_callable}
                Expected: {"on_start_game", "on_action"}
        """
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

        # Active game logs
        self.game_logs: dict[str, GameLog] = {}

        # Create FastMCP instance
        self.mcp = FastMCP(
            name=f"Agent-{role.capitalize()}",
            instructions=f"{role.capitalize()} agent with crewAI orchestration",
        )

        # Register tools
        self._register_tools()

    def _register_tools(self) -> None:
        """Register MCP tools."""

        @self.mcp.tool()
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
                self.role,
                self.secret,
                self.config_sha256,
                self.games_dir,
                self.game_logs,
                self.handler_callbacks,
                message_json,
                signature,
            )

        @self.mcp.tool()
        def action(
            game_id: Annotated[
                str,
                Field(
                    description=(
                        "Unique identifier of the active game session, "
                        "as returned by start_game."
                    )
                ),
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
                        "reveal: move (N/S/E/W/STAY), hint (≤15 words), intent (truth|lie), nonce; "
                        "final_audit: nonces (dict of step→nonce). "
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
            """Execute a game action for any protocol phase.

            Handles all phases of the commit-reveal protocol:
              commit      — agent receives a state snapshot and returns h_commit
              reveal      — agent reveals its move, hint, intent, and nonce
              final_audit — agent returns all nonces for tamper verification
              game_end    — notify agent the game is over

            Returns:
                {"ok": true/false, "error": str, "phase": str}
            """
            return handle_action(
                self.role,
                self.secret,
                self.config_sha256,
                self.games_dir,
                self.game_logs,
                self.handler_callbacks,
                game_id,
                message_json,
                signature,
            )

        @self.mcp.tool()
        def ping() -> dict:
            """Health check — confirms the agent is running and ready.

            Call this before start_game to verify the agent is reachable.

            Returns:
                {"ok": true, "role": str}
            """
            return {"ok": True, "role": self.role}

        @self.mcp.tool()
        def get_config() -> dict:
            """Return this agent's agreed config hash and protocol version.

            Remote agents call this before start_game to confirm both sides
            loaded the same game_config (identified by its SHA-256 hash).
            The shared secret is NOT included in this response.

            Returns:
                {"config_sha256": str, "protocol_version": str, "role": str}
            """
            return {
                "config_sha256": self.config_sha256,
                "protocol_version": "1.0",
                "role": self.role,
            }

        @self.mcp.tool()
        def get_protocol() -> dict:
            """Return the full protocol definition for this agent.

            Remote agents call this during MCP discovery to learn the exact
            field names used inside game message payloads, signing scheme, and
            payload encoding — so they can translate their internal representation
            to the format this agent expects.

            The `fields` dict maps canonical concept name → the actual JSON field
            name this agent uses. For standard agents these are identical (identity
            map). A non-standard peer may use e.g. "turn" instead of "step".

            Returns:
                {
                  "protocol": "cop-thief-commit-reveal",
                  "version": "1.0",
                  "signing": {"required": bool, "algorithm": str, ...},
                  "payload_encoding": "json_string" | "object",
                  "fields": {<concept>: <field_name>, ...}
                }
            """
            return {
                "protocol": "cop-thief-commit-reveal",
                "version": "1.0",
                "signing": {
                    "required": True,
                    "algorithm": "hmac-sha256",
                    "encoding": "hex",
                    "canonical_json": True,
                },
                "payload_encoding": "json_string",
                "fields": {
                    "game_id":       "game_id",
                    "gamelet":       "gamelet",
                    "step":          "step",
                    "role":          "role",
                    "phase":         "phase",
                    "config_sha256": "config_sha256",
                    "state_hash":    "state_hash",
                    "h_commit":      "h_commit",
                    "h_commit_ack":  "h_commit_ack",
                    "move":          "move",
                    "hint":          "hint",
                    "intent":        "intent",
                    "nonce":         "nonce",
                    "nonces":        "nonces",
                    "timestamp":     "timestamp",
                },
            }

    def get_game_log(self, game_id: str) -> GameLog | None:
        """Get log for a game.

        Args:
            game_id: Game identifier.

        Returns:
            GameLog or None if not found.
        """
        return self.game_logs.get(game_id)

    async def run_async(self, host: str = "localhost", port: int = 5000) -> None:
        """Run server asynchronously.

        Args:
            host: Hostname to bind to.
            port: Port to listen on.
        """
        logger.info(f"Starting Agent MCP server on {host}:{port}")
        await self.mcp.run_async(
            transport="sse",
            host=host,
            port=port,
        )
