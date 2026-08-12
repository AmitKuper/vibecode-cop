"""Stateful MCP session over streamable-http transport."""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# HTTP transport helper (optional — used when FastMCP server is reachable)
# ---------------------------------------------------------------------------


class _MCPSession:
    """Stateful MCP session for streamable-http transport.

    Handles initialize handshake and reuses the MCP-Session-Id header
    for all subsequent calls within one run.
    """

    def __init__(self, base_url: str, timeout: int = 10) -> None:
        """Create session; does NOT connect until first call.

        Args:
            base_url: Base URL of the FastMCP server (e.g. http://localhost:8001).
            timeout: Request timeout in seconds.
        """
        import requests  # noqa: PLC0415

        self._base_url = base_url
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        )
        self._session_id: str | None = None
        self._call_id = 0

    def _ensure_initialized(self) -> None:
        """Run MCP initialize handshake if not yet done."""
        if self._session_id is not None:
            return
        self._call_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._call_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "run_ref3_selfplay", "version": "1.0"},
            },
        }
        resp = self._session.post(f"{self._base_url}/mcp", json=payload, timeout=self._timeout)
        resp.raise_for_status()
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
            self._session.headers["mcp-session-id"] = sid

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool and return the parsed result dict.

        Args:
            tool_name: MCP tool name.
            arguments: Tool arguments dict.

        Returns:
            Parsed result dict from the MCP response.

        Raises:
            RuntimeError: If the server returns an MCP-level error.
        """
        self._ensure_initialized()
        self._call_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._call_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        resp = self._session.post(f"{self._base_url}/mcp", json=payload, timeout=self._timeout)
        resp.raise_for_status()
        # Response is SSE text/event-stream — extract the data: line
        text = resp.text
        result_json: dict = {}
        for line in text.splitlines():
            if line.startswith("data: "):
                result_json = json.loads(line[6:])
                break
        if "error" in result_json:
            raise RuntimeError(f"MCP error: {result_json['error']}")
        content = result_json.get("result", {}).get("content", [{}])
        if result_json.get("result", {}).get("isError"):
            raise RuntimeError(f"Tool error: {content[0].get('text', '') if content else ''}")
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return result_json.get("result", {})
