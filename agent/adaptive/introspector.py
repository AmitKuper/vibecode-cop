"""MCPIntrospector: collect tools, schemas, and capabilities from a remote MCP server.

Uses standard MCP initialization + tools/list. Treats all remote descriptions as
untrusted data and defends against prompt injection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from agent.adaptive.transport_probe import ProbeResult, TransportType

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = [
    r"ignore\s+previous",
    r"disregard\s+(all|prior|above)",
    r"you\s+are\s+now",
    r"system\s*:\s*",
    r"<\|im_start\|>",
    r"\[\s*INST\s*\]",
    r"forget\s+(everything|all)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def _sanitize(text: str | None) -> str:
    text = text or ""
    if _INJECTION_RE.search(text):
        raise ValueError(f"Prompt injection detected in remote description: {text[:120]!r}")
    return text


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict
    output_schema: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    def schema_digest(self) -> str:
        blob = json.dumps(
            {
                "name": self.name,
                "input_schema": self.input_schema,
                "output_schema": self.output_schema,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


@dataclass
class IntrospectionResult:
    server_name: str
    server_version: str
    protocol_version: str
    tools: list[ToolSchema]
    resources: list[dict]
    prompts: list[dict]
    raw_capabilities: dict
    schema_digest: str

    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]

    def get_tool(self, name: str) -> ToolSchema | None:
        return next((t for t in self.tools if t.name == name), None)


class MCPIntrospector:
    """Introspects a remote MCP server via initialize + tools/list.

    Does not send any game data. Detects prompt injection in descriptions.
    """

    def __init__(self, timeout_s: float = 10.0) -> None:
        self._timeout = timeout_s

    async def introspect(self, probe: ProbeResult) -> IntrospectionResult:
        if probe.transport == TransportType.STDIO:
            return await self._stdio_introspect(probe)
        if probe.transport == TransportType.SSE:
            return await self._sse_introspect(probe)
        return await self._http_introspect(probe)

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

    def _build_result(
        self,
        init_body: dict,
        raw_tools: list[dict],
        resources: list[dict],
        prompts: list[dict],
    ) -> IntrospectionResult:
        server_info = init_body.get("serverInfo", {})
        capabilities = init_body.get("capabilities", {})
        tools = []
        for rt in raw_tools:
            desc = _sanitize(rt.get("description", ""))
            tools.append(
                ToolSchema(
                    name=rt["name"],
                    description=desc,
                    input_schema=rt.get("inputSchema", {}),
                    output_schema=rt.get("outputSchema", {}),
                    raw=rt,
                )
            )

        all_digests = "|".join(sorted(t.schema_digest() for t in tools))
        schema_digest = hashlib.sha256(all_digests.encode()).hexdigest()

        return IntrospectionResult(
            server_name=server_info.get("name", "unknown"),
            server_version=server_info.get("version", "0.0.0"),
            protocol_version=init_body.get("protocolVersion", "unknown"),
            tools=tools,
            resources=resources,
            prompts=prompts,
            raw_capabilities=capabilities,
            schema_digest=schema_digest,
        )

    def _parse_response(self, resp: httpx.Response) -> dict:
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        text = resp.text

        # SSE: extract data: line
        if "event-stream" in ct:
            for line in text.splitlines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    return payload.get("result", payload)
            raise ValueError("No data: line in SSE response")

        payload = resp.json()
        if "error" in payload:
            raise ValueError(f"MCP error: {payload['error']}")
        return payload.get("result", payload)

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

    def introspect_sync(self, probe: ProbeResult) -> IntrospectionResult:
        import asyncio

        return asyncio.run(self.introspect(probe))
