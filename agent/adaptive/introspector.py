"""MCPIntrospector: collect tools, schemas, and capabilities from a remote MCP server.

Uses standard MCP initialization + tools/list. Treats all remote descriptions as
untrusted data and defends against prompt injection.
"""

from __future__ import annotations

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


def _sanitize(text: str) -> str:
    if _INJECTION_RE.search(text):
        raise ValueError(f"Prompt injection detected in remote description: {text[:120]!r}")
    return text


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict
    raw: dict = field(default_factory=dict)

    def schema_digest(self) -> str:
        blob = json.dumps(
            {"name": self.name, "input_schema": self.input_schema},
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
            return self._stdio_fallback()
        return await self._http_introspect(probe)

    async def _http_introspect(self, probe: ProbeResult) -> IntrospectionResult:
        endpoint = probe.mcp_endpoint
        is_sse = probe.transport == TransportType.SSE

        # For SSE transport, MCP messages go to the messages endpoint
        post_url = endpoint if not is_sse else endpoint.replace("/sse", "/messages")

        async with httpx.AsyncClient(timeout=self._timeout) as c:
            # Step 1: initialize
            init_resp = await c.post(
                post_url if not is_sse else endpoint,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "clientInfo": {"name": "introspector", "version": "1.0"},
                    },
                },
                headers={"Accept": "application/json, text/event-stream"},
            )
            init_body = self._parse_response(init_resp)
            server_info = init_body.get("serverInfo", {})
            capabilities = init_body.get("capabilities", {})

            # Step 2: tools/list
            tools_resp = await c.post(
                post_url if not is_sse else endpoint,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers={"Accept": "application/json, text/event-stream"},
            )
            tools_body = self._parse_response(tools_resp)
            raw_tools = tools_body.get("tools", [])

            # Step 3: resources/list (optional)
            resources: list[dict] = []
            prompts: list[dict] = []
            try:
                res_resp = await c.post(
                    post_url if not is_sse else endpoint,
                    json={"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}},
                    headers={"Accept": "application/json"},
                )
                resources = self._parse_response(res_resp).get("resources", [])
            except Exception:
                pass

        tools = []
        for rt in raw_tools:
            try:
                desc = _sanitize(rt.get("description", ""))
                tools.append(
                    ToolSchema(
                        name=rt["name"],
                        description=desc,
                        input_schema=rt.get("inputSchema", {}),
                        raw=rt,
                    )
                )
            except ValueError as exc:
                logger.warning("Skipping tool %s: %s", rt.get("name"), exc)

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

    def introspect_sync(self, probe: ProbeResult) -> IntrospectionResult:
        import asyncio
        return asyncio.run(self.introspect(probe))
