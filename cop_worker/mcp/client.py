"""MCP client for calling opponent's tools via fastmcp SSE transport."""

import asyncio
import logging

from fastmcp import Client
from fastmcp.client.transports import SSETransport, StdioTransport, StreamableHttpTransport

from cop_worker.crypto import canonical_json, sign_message
from cop_worker.mcp.messages import ActionMessage, StartGameMessage
from cop_worker.protocol.transport_probe import normalize_mcp_base_url

logger = logging.getLogger(__name__)


class GameMCPClient:
    """Client to call opponent's MCP tools using fastmcp SSE transport."""

    def __init__(
        self,
        peer_url: str,
        secret: str,
        timeout_seconds: float = 30.0,
    ):
        """Initialize MCP client.

        Args:
            peer_url: Opponent's MCP SSE endpoint (http://localhost:5001/mcp)
            secret: Shared secret for HMAC
            timeout_seconds: Timeout for remote calls
        """
        self.peer_url = peer_url
        self.secret = secret
        self.timeout = timeout_seconds
        # SSE transport connects to /sse endpoint
        sse_url = normalize_mcp_base_url(peer_url) + "/sse"
        self._transport = SSETransport(sse_url)

    def configure_transport(
        self, transport: str, endpoint: str, stdio_command: tuple[str, ...] = ()
    ) -> None:
        """Use the exact endpoint selected by pre-game transport discovery."""
        if transport == "sse":
            self._transport = SSETransport(endpoint)
        elif transport == "streamable_http":
            self._transport = StreamableHttpTransport(endpoint)
        elif transport == "stdio" and stdio_command:
            self._transport = StdioTransport(stdio_command[0], list(stdio_command[1:]))
        else:
            raise ValueError(f"Unsupported remote gameplay transport: {transport}")

    async def start_game(self, msg: StartGameMessage) -> dict:
        """Call opponent's start_game tool.

        Args:
            msg: StartGameMessage

        Returns:
            Response dict from opponent
        """
        message_json = canonical_json(msg.to_dict())
        signature = sign_message(msg.to_dict(), self.secret)

        logger.info(f"Calling start_game on {self.peer_url}: game_id={msg.game_id}")

        return await self._call_tool(
            "start_game",
            {
                "message_json": message_json,
                "signature": signature,
            },
        )

    async def action(self, game_id: str, msg: ActionMessage) -> dict:
        """Call opponent's action tool.

        Args:
            game_id: Game identifier
            msg: ActionMessage

        Returns:
            Response dict from opponent
        """
        message_json = canonical_json(msg.to_dict())
        signature = sign_message(msg.to_dict(), self.secret)

        logger.debug(
            f"Calling action on {self.peer_url}: game_id={game_id}, "
            f"phase={msg.phase}, step={msg.step}"
        )

        return await self._call_tool(
            "action",
            {
                "game_id": game_id,
                "message_json": message_json,
                "signature": signature,
            },
        )

    async def ping(self) -> dict:
        """Call opponent's ping tool for health check.

        Returns:
            Response dict from opponent
        """
        logger.debug(f"Pinging {self.peer_url}")
        return await self._call_tool("ping", {})

    async def _call_tool(self, tool_name: str, params: dict) -> dict:
        """Call a tool on opponent's MCP server via SSE transport.

        Args:
            tool_name: Name of MCP tool
            params: Tool parameters

        Returns:
            Tool result dict

        Raises:
            Exception: If call fails
        """
        try:
            async with Client(self._transport) as client:
                result = await asyncio.wait_for(
                    client.call_tool(tool_name, params),
                    timeout=self.timeout,
                )

                # fastmcp returns CallToolResult with .content list
                # Each content item has .text for TextContent
                if result.content:
                    import json

                    item = result.content[0]
                    text = item.text if hasattr(item, "text") else str(item)
                    if getattr(result, "is_error", False) is True:
                        return {"ok": False, "error": text}
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return {"ok": True, "raw": text}
                return {"ok": getattr(result, "is_error", False) is not True}

        except Exception as e:
            logger.error(f"MCP call to {tool_name} failed: {e}")
            raise
