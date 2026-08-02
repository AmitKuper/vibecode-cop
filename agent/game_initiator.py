"""Game initiator - starts a new game between cop and thief agents."""

import asyncio
import logging
import uuid
from datetime import datetime

from agent.game_initiator_handshake import call_start_game, wait_for_readiness
from agent.mcp.client import GameMCPClient
from agent.mcp.messages import StartGameMessage

logger = logging.getLogger(__name__)


class GameInitiator:
    """Initiates games between cop and thief agents."""

    def __init__(
        self,
        cop_url: str = "http://localhost:5000/mcp",
        thief_url: str = "http://localhost:5001/mcp",
        secret: str = "dev-secret-change-me",
        config_sha256: str = "default-config-hash",
    ):
        self.cop_url = cop_url
        self.thief_url = thief_url
        self.secret = secret
        self.config_sha256 = config_sha256
        # start_game triggers MCP discovery (LLM call can take 60-90s)
        self.cop_client = GameMCPClient(cop_url, secret, timeout_seconds=120.0)
        self.thief_client = GameMCPClient(thief_url, secret, timeout_seconds=120.0)

    async def start_game(self, game_id: str = None, timeout_seconds: float = 30.0) -> dict:
        """Start a new game between cop and thief. Returns dict with game_id and result."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        game_id = game_id or f"game_{ts}_{uuid.uuid4().hex[:8]}"
        logger.info(f"Starting game: {game_id}")
        logger.info(f"  Cop URL: {self.cop_url}")
        logger.info(f"  Thief URL: {self.thief_url}")
        await wait_for_readiness(self.cop_client, "cop", timeout_seconds=10.0)
        await wait_for_readiness(self.thief_client, "thief", timeout_seconds=10.0)
        logger.info("Both agents ready, initiating game...")
        try:
            cop_base = self.cop_url.rstrip("/").replace("/mcp", "")
            thief_base = self.thief_url.rstrip("/").replace("/mcp", "")
            cop_response = await call_start_game(
                self.cop_client,
                StartGameMessage(
                    game_id=game_id,
                    roles={"cop": "cop", "thief": "thief"},
                    config_sha256=self.config_sha256,
                    protocol_version="1.0",
                    endpoint=cop_base,
                    timestamp=datetime.now().isoformat(),
                    peer_url=thief_base,
                ),
                "cop",
                self.secret,
            )
            if not cop_response.get("ok"):
                logger.error(f"Cop rejected game: {cop_response}")
                return {
                    "ok": False,
                    "game_id": game_id,
                    "error": f"Cop rejected: {cop_response.get('error')}",
                }
            logger.info("Cop accepted game")
            thief_response = await call_start_game(
                self.thief_client,
                StartGameMessage(
                    game_id=game_id,
                    roles={"cop": "cop", "thief": "thief"},
                    config_sha256=self.config_sha256,
                    protocol_version="1.0",
                    endpoint=thief_base,
                    timestamp=datetime.now().isoformat(),
                    peer_url=cop_base,
                ),
                "thief",
                self.secret,
            )
            if not thief_response.get("ok"):
                logger.error(f"Thief rejected game: {thief_response}")
                return {
                    "ok": False,
                    "game_id": game_id,
                    "error": f"Thief rejected: {thief_response.get('error')}",
                }
            logger.info(f"Game {game_id} started successfully!")
            return {
                "ok": True,
                "game_id": game_id,
                "cop_response": cop_response,
                "thief_response": thief_response,
            }
        except TimeoutError:
            logger.error("Game initiation timeout")
            return {"ok": False, "game_id": game_id, "error": "Handshake timeout"}
        except Exception as e:
            logger.error(f"Game initiation failed: {e}", exc_info=True)
            return {"ok": False, "game_id": game_id, "error": str(e)}

    async def _wait_for_readiness(
        self, client: GameMCPClient, role: str, timeout_seconds: float = 10.0
    ) -> bool:
        return await wait_for_readiness(client, role, timeout_seconds)

    async def _call_start_game(
        self, client: GameMCPClient, message: StartGameMessage, role: str
    ) -> dict:
        return await call_start_game(client, message, role, self.secret)


if __name__ == "__main__":
    import sys

    from agent.game_initiator_handshake import main

    sys.exit(asyncio.run(main()))
