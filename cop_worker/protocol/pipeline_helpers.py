"""Adaptive-negotiation helpers: tool caller, sync wrapper, native adapter,
schema re-verification."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from cop_worker.protocol.adapter import DeterministicProtocolAdapter, ProtocolCompatibilityError
from cop_worker.protocol.introspector import MCPIntrospector
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan
from cop_worker.protocol.pipeline import (
    AdaptiveNegotiationResult,
    run_adaptive_negotiation,
)
from cop_worker.protocol.profile import ProtocolProfile
from cop_worker.protocol.transport_probe import TransportType

logger = logging.getLogger(__name__)


def _discovered_tool_caller(probe):
    """Build a caller for the transport that was actually negotiated."""
    from fastmcp import Client
    from fastmcp.client.transports import SSETransport, StreamableHttpTransport

    if probe.transport == TransportType.SSE:
        transport = SSETransport(probe.mcp_endpoint)
    elif probe.transport == TransportType.STREAMABLE_HTTP:
        transport = StreamableHttpTransport(probe.mcp_endpoint)
    elif probe.transport == TransportType.STDIO and probe.stdio_command:
        from fastmcp.client.transports import StdioTransport

        transport = StdioTransport(probe.stdio_command[0], list(probe.stdio_command[1:]))
    else:
        raise ProtocolCompatibilityError(f"No remote caller for {probe.transport}")

    async def call(tool_name: str, params: dict) -> dict:
        async with Client(transport) as client:
            result = await client.call_tool(tool_name, params)
        if not result.content:
            return {"ok": getattr(result, "is_error", False) is not True}
        item = result.content[0]
        value = item.text if hasattr(item, "text") else str(item)
        if getattr(result, "is_error", False) is True:
            return {"ok": False, "error": value}
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {"ok": True, "raw": value}
        return parsed if isinstance(parsed, dict) else {"ok": True, "raw": parsed}

    return call


def run_adaptive_negotiation_sync(
    opponent_url: str,
    llm: Any = None,
    cache_dir: Path | None = None,
) -> AdaptiveNegotiationResult:
    """Synchronous wrapper for run_adaptive_negotiation."""
    return asyncio.run(run_adaptive_negotiation(opponent_url, llm=llm, cache_dir=cache_dir))


def native_adapter() -> AdaptiveNegotiationResult:
    """Return an identity adapter for a native canonical server."""
    plan = ProtocolMappingPlan.native_plan()
    profile = ProtocolProfile.native()
    adapter = DeterministicProtocolAdapter(plan)
    return AdaptiveNegotiationResult(profile, adapter)


async def verify_locked_schema(profile: ProtocolProfile, timeout_s: float = 10.0) -> None:
    """Re-introspect without an LLM and abort if a locked peer schema changed."""
    from cop_worker.protocol.transport_probe import ProbeResult

    probe = ProbeResult(
        transport=TransportType(profile.remote_transport),
        base_url=profile.remote_endpoint,
        mcp_endpoint=profile.remote_endpoint,
        latency_ms=0.0,
        probe_notes="locked-profile recheck",
        stdio_command=profile.remote_stdio_command,
    )
    current = await MCPIntrospector(timeout_s=timeout_s).introspect(probe)
    if current.schema_digest != profile.remote_schema_digest:
        raise ProtocolCompatibilityError(
            "Remote schema changed after ProtocolProfile lock: "
            f"{profile.remote_schema_digest} != {current.schema_digest}"
        )
