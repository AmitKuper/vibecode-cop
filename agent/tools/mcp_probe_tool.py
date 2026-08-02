"""crewAI tool: probe a remote MCP server and return its tool schemas as JSON.

Transport auto-detection order:
  {peer_url}/sse          (FastMCP default)
  {peer_url}/mcp/sse      (MCP-over-HTTP convention)
  {peer_url}/v1/sse       (versioned variant)
  {peer_url}              (StreamableHTTP or bare SSE)

If the peer exposes a `get_protocol` tool, it is called automatically and the
result is included as `protocol_def` in the probe output. This enables the
explorer agent to extract the peer's canonical field name mapping.
"""

import asyncio
import json
import logging

from crewai.tools import tool

logger = logging.getLogger(__name__)

_SSE_SUFFIXES = ["/sse", "/mcp/sse", "/v1/sse", ""]


def _probe_sync(peer_url: str) -> tuple[str, dict, dict | None]:
    """Auto-detect SSE transport, list_tools, optionally call get_protocol.

    Returns (transport_url, schemas_dict, protocol_def_or_None).
    protocol_def is the parsed JSON from get_protocol() if that tool exists.
    """
    from fastmcp import Client
    from fastmcp.client.transports import SSETransport

    base = peer_url.rstrip("/")

    async def _run() -> tuple[str, dict, dict | None]:
        for suffix in _SSE_SUFFIXES:
            url = base + suffix
            try:
                async with Client(SSETransport(url)) as client:
                    tools = await client.list_tools()
                    schemas = {
                        t.name: {
                            "name": t.name,
                            "description": t.description or "",
                            "input_schema": t.inputSchema or {},
                        }
                        for t in tools
                    }

                    # Call get_protocol() if the peer exposes it
                    protocol_def: dict | None = None
                    if "get_protocol" in schemas:
                        try:
                            r = await client.call_tool("get_protocol", {})
                            if r.content:
                                text = (
                                    r.content[0].text
                                    if hasattr(r.content[0], "text")
                                    else str(r.content[0])
                                )
                                protocol_def = json.loads(text)
                                logger.info(
                                    "[probe] get_protocol() → "
                                    f"protocol={protocol_def.get('protocol')}, "
                                    f"fields={list(protocol_def.get('fields', {}))[:5]}..."
                                )
                        except Exception as exc:
                            logger.warning(f"[probe] get_protocol() call failed: {exc}")

                    logger.info(f"[probe] Transport found at {url}")
                    return url, schemas, protocol_def

            except Exception:
                continue

        raise RuntimeError(
            f"No reachable SSE endpoint found for {peer_url}. "
            f"Tried: {[base + s for s in _SSE_SUFFIXES]}"
        )

    return asyncio.run(_run())


@tool
def probe_mcp_server(peer_url: str) -> str:
    """Probe a remote MCP server and return its tool list with schemas.

    Auto-detects the SSE transport URL by trying common path suffixes.
    If the peer exposes a `get_protocol` tool, calls it and includes the
    result as `protocol_def` — this contains the peer's canonical field name
    mapping (fields), signing requirements, and payload encoding.

    Use `protocol_def.fields` to build the `field_map` for the skill:
    keys are canonical concept names (game_id, step, role, h_commit, move,
    hint, intent, nonce, …), values are the actual JSON field names the peer
    uses in its message payloads.

    Args:
        peer_url: Base URL of the remote MCP server (e.g. http://localhost:5000).

    Returns:
        JSON string with keys: peer_url, transport_url, tools, protocol_def.
    """
    base = peer_url.rstrip("/")
    logger.info(f"[probe_mcp_server] Probing {base}")
    try:
        transport_url, schemas, protocol_def = _probe_sync(base)
        logger.info(f"[probe_mcp_server] Found {len(schemas)} tools: {list(schemas)}")
        return json.dumps(
            {
                "peer_url": base,
                "transport_url": transport_url,
                "tools": schemas,
                "protocol_def": protocol_def,
            },
            indent=2,
        )
    except Exception as exc:
        logger.error(f"[probe_mcp_server] Failed: {exc}")
        raise RuntimeError(f"MCP probe failed for {peer_url}: {exc}") from exc
