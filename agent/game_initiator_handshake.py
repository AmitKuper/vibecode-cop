"""Handshake flow helpers for GameInitiator."""

import asyncio
import logging

from agent.mcp.client import GameMCPClient
from agent.mcp.crypto import canonical_json, sign_message
from agent.mcp.messages import StartGameMessage

logger = logging.getLogger(__name__)


async def wait_for_readiness(
    client: GameMCPClient, role: str, timeout_seconds: float = 10.0
) -> bool:
    """Wait for an agent to be ready (ping succeeds).

    Args:
        client: GameMCPClient to ping
        role: Agent role (for logging)
        timeout_seconds: How long to wait

    Returns:
        True if ready, False if timeout
    """
    import time

    start_time = time.time()
    retry_count = 0
    wait_time = 0.5  # Start with 500ms

    while time.time() - start_time < timeout_seconds:
        try:
            result = await client._call_tool("ping", {})
            if result.get("ok"):
                logger.info(f"{role.capitalize()} agent is ready")
                return True
        except Exception:
            retry_count += 1
            if retry_count % 5 == 0:  # Log every 5 retries
                logger.debug(f"Waiting for {role}... (attempt {retry_count})")

        # Exponential backoff with max 2 seconds
        await asyncio.sleep(min(wait_time, 2.0))
        wait_time *= 1.5

    logger.warning(
        f"Timeout waiting for {role} agent to be ready (after {timeout_seconds}s)"
    )
    return False


async def call_start_game(
    client: GameMCPClient,
    message: StartGameMessage,
    role: str,
    secret: str,
) -> dict:
    """Call start_game on remote agent.

    Args:
        client: MCP client
        message: StartGameMessage
        role: "cop" or "thief" (for logging)
        secret: Shared secret for signing

    Returns:
        Response dict
    """
    try:
        # Serialize and sign message
        message_json = canonical_json(message.to_dict())
        signature = sign_message(message.to_dict(), secret)

        logger.debug(f"Calling start_game on {role}: {message.game_id}")

        # Call via MCP client (using internal _call_tool)
        result = await client._call_tool(
            "start_game",
            {
                "message_json": message_json,
                "signature": signature,
            },
        )

        return result

    except Exception as e:
        logger.error(f"Failed to call start_game on {role}: {e}", exc_info=True)
        raise


async def main() -> int:
    """Main entry point - start a game."""
    import sys

    from agent.game_initiator import GameInitiator

    # Get game ID from command line (optional)
    game_id = sys.argv[1] if len(sys.argv) > 1 else None

    # Create initiator
    initiator = GameInitiator(
        cop_url="http://localhost:5000/mcp",
        thief_url="http://localhost:5001/mcp",
        secret="dev-secret-change-me",
        config_sha256="default-config-hash",
    )

    # Start game
    result = await initiator.start_game(game_id=game_id)

    # Print result
    print("\n" + "=" * 60)
    print(f"Game Initiation Result: {result}")
    print("=" * 60)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
