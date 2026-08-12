"""HTTP tool-call routing and endpoint probing."""

from __future__ import annotations

from ref3_selfplay.session import _MCPSession

# Module-level HTTP sessions, created lazily when HTTP transport is active
_cop_session: _MCPSession | None = None
_thief_session: _MCPSession | None = None


def _call_tool_http(base_url: str, tool_name: str, arguments: dict, timeout: int = 10) -> dict:
    """Call an MCP tool via HTTP POST (streamable-http transport).

    Args:
        base_url: Base URL of the FastMCP server (e.g. http://localhost:8001).
        tool_name: MCP tool name.
        arguments: Tool arguments dict.
        timeout: Request timeout in seconds.

    Returns:
        Parsed result dict from the MCP response.

    Raises:
        RuntimeError: If the server returns an MCP-level error.
    """
    global _cop_session, _thief_session  # noqa: PLW0603
    if "8001" in base_url:
        if _cop_session is None:
            _cop_session = _MCPSession(base_url, timeout)
        return _cop_session.call_tool(tool_name, arguments)
    else:
        if _thief_session is None:
            _thief_session = _MCPSession(base_url, timeout)
        return _thief_session.call_tool(tool_name, arguments)


def _probe_http(url: str) -> bool:
    """Return True if the FastMCP server at url/mcp responds to POST initialize.

    Args:
        url: Base URL to probe.

    Returns:
        True if reachable, False otherwise.
    """
    try:
        import requests  # noqa: PLC0415

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "1.0"},
            },
        }
        r = requests.post(f"{url}/mcp", json=payload, headers=headers, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# HTTP transport probe (bonus: real HTTP if FastMCP is running)
# ---------------------------------------------------------------------------


def _try_real_http_probe() -> dict:
    """Probe both cop_worker and thief_worker HTTP endpoints.

    Returns:
        Dict with 'cop_reachable', 'thief_reachable', 'cop_url', 'thief_url'.
    """
    cop_url = "http://localhost:8001"
    thief_url = "http://localhost:8002"
    return {
        "cop_reachable": _probe_http(cop_url),
        "thief_reachable": _probe_http(thief_url),
        "cop_url": cop_url,
        "thief_url": thief_url,
    }
