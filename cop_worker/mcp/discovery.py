"""MCP Protocol Discovery - dynamically understand opponent's MCP interface."""

import logging

from fastmcp import Client
from fastmcp.client.transports import SSETransport

logger = logging.getLogger(__name__)


class ProtocolDiscovery:
    """Discovers available tools and their schemas from remote MCP server via SSE."""

    def __init__(self, peer_url: str, timeout_seconds: float = 30.0):
        """Initialize protocol discovery.

        Args:
            peer_url: Opponent's MCP SSE endpoint (http://localhost:5001/mcp)
            timeout_seconds: Timeout for discovery calls
        """
        self.peer_url = peer_url
        self.timeout = timeout_seconds
        self.tools: dict[str, dict] = {}  # tool_name -> schema
        self.discovered = False
        # SSE transport connects to /sse endpoint
        self._sse_url = peer_url.rstrip("/").replace("/mcp", "") + "/sse"

    async def discover(self) -> bool:
        """Discover available tools from opponent's MCP server via SSE.

        Returns:
            True if discovery succeeded, False otherwise
        """
        try:
            logger.info(f"Discovering MCP protocol from {self.peer_url}")

            transport = SSETransport(self._sse_url)
            async with Client(transport) as client:
                tools = await client.list_tools()
                for tool in tools:
                    self.tools[tool.name] = {
                        "name": tool.name,
                        "description": tool.description,
                        "schema": tool.inputSchema,
                    }

            logger.info(f"Discovered {len(self.tools)} tools: {list(self.tools.keys())}")
            self.discovered = True
            return True

        except Exception as e:
            logger.warning(f"Protocol discovery failed: {e}")
            return False

    def get_tool_names(self) -> list[str]:
        """Get list of discovered tool names."""
        return list(self.tools.keys())

    def has_tool(self, tool_name: str) -> bool:
        """Check if a specific tool is available."""
        return tool_name in self.tools

    def get_tool_schema(self, tool_name: str) -> dict | None:
        """Get schema for a tool."""
        return self.tools.get(tool_name)

    def validate_protocol(self, required_tools: list[str]) -> tuple[bool, str]:
        """Validate that all required tools are available."""
        missing = [t for t in required_tools if t not in self.tools]
        if missing:
            return False, f"Missing required tools: {missing}"
        return True, "All required tools available"

    def to_dict(self) -> dict:
        """Serialize discovered protocol to dict."""
        return {
            "discovered": self.discovered,
            "tools": list(self.tools.keys()),
            "tool_schemas": self.tools,
        }
