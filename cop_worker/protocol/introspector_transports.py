"""MCPIntrospector transport methods: SSE, HTTP, stdio (mixin)."""

from __future__ import annotations

import asyncio
import logging

from cop_worker.protocol.introspector_types import (  # noqa: F401  (public re-exports)
    _INJECTION_PATTERNS,
    _INJECTION_RE,
    IntrospectionResult,
    ToolSchema,
    _sanitize,
    _sanitize_tree,
)
from cop_worker.protocol.transport_probe import ProbeResult

logger = logging.getLogger(__name__)


class IntrospectorTransportsMixin:
    """Transport-specific introspection attempts."""

    async def _sse_introspect(self, probe: ProbeResult) -> IntrospectionResult:
        """Use the MCP client's negotiated SSE message endpoint.

        The `/sse` URL is only the long-lived receive stream. A session-specific
        POST endpoint is announced inside that stream, so posting JSON-RPC
        directly to `/sse` is invalid on compliant legacy servers.
        """
        from fastmcp import Client
        from fastmcp.client.transports import SSETransport

        async with Client(SSETransport(probe.mcp_endpoint)) as client:
            raw_tool_models = await asyncio.wait_for(client.list_tools(), self._timeout)
            resources: list[dict] = []
            prompts: list[dict] = []
            try:
                resource_models = await asyncio.wait_for(client.list_resources(), self._timeout)
                resources = [item.model_dump(by_alias=True) for item in resource_models]
            except Exception:
                pass
            try:
                prompt_models = await asyncio.wait_for(client.list_prompts(), self._timeout)
                prompts = [item.model_dump(by_alias=True) for item in prompt_models]
            except Exception:
                pass
            init_model = client.initialize_result
            init_body = init_model.model_dump(by_alias=True) if init_model is not None else {}

        raw_tools = [item.model_dump(by_alias=True) for item in raw_tool_models]
        return self._build_result(init_body, raw_tools, resources, prompts)

    async def _http_introspect(self, probe: ProbeResult) -> IntrospectionResult:
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport

        async with Client(StreamableHttpTransport(probe.mcp_endpoint)) as client:
            raw_tool_models = await asyncio.wait_for(client.list_tools(), self._timeout)
            resources: list[dict] = []
            prompts: list[dict] = []
            try:
                models = await asyncio.wait_for(client.list_resources(), self._timeout)
                resources = [item.model_dump(by_alias=True) for item in models]
            except Exception:
                pass
            try:
                models = await asyncio.wait_for(client.list_prompts(), self._timeout)
                prompts = [item.model_dump(by_alias=True) for item in models]
            except Exception:
                pass
            init_model = client.initialize_result
            init_body = init_model.model_dump(by_alias=True) if init_model is not None else {}
        raw_tools = [item.model_dump(by_alias=True) for item in raw_tool_models]
        return self._build_result(init_body, raw_tools, resources, prompts)

    def _stdio_fallback(self) -> IntrospectionResult:
        return IntrospectionResult(
            server_name="stdio-fixture",
            server_version="1.0",
            protocol_version="2024-11-05",
            tools=[],
            resources=[],
            prompts=[],
            raw_capabilities={},
            schema_digest="stdio-fixture",
        )

    async def _stdio_introspect(self, probe: ProbeResult) -> IntrospectionResult:
        if not probe.stdio_command:
            return self._stdio_fallback()
        from fastmcp import Client
        from fastmcp.client.transports import StdioTransport

        transport = StdioTransport(probe.stdio_command[0], list(probe.stdio_command[1:]))
        async with Client(transport) as client:
            models = await asyncio.wait_for(client.list_tools(), self._timeout)
            init_model = client.initialize_result
            init_body = init_model.model_dump(by_alias=True) if init_model is not None else {}
        raw_tools = [item.model_dump(by_alias=True) for item in models]
        return self._build_result(init_body, raw_tools, [], [])
