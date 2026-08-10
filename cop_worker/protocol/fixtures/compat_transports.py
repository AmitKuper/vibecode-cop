"""Compatible fixtures: transport stubs (streamable HTTP, SSE, stdio)."""

from __future__ import annotations

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.helpers import _intro, _tool
from cop_worker.protocol.introspector import IntrospectionResult
from cop_worker.protocol.mapping_plan import (
    ProtocolMappingPlan,
)


def fixture_streamable_http() -> Fixture:
    return Fixture(
        name="streamable_http",
        description="Streamable HTTP transport (stub compatible fixture)",
        compatible=True,
        introspection=_intro(
            "streamable-http-server",
            [
                _tool(
                    "action",
                    "Streamable HTTP action",
                    {
                        "game_id": "string",
                        "step": "integer",
                        "role": "string",
                        "phase": "string",
                        "commitment": "string",
                        "move": "string",
                        "nonces": "object",
                        "config_sha256": "string",
                    },
                )
            ],
        ),
        expected_plan=ProtocolMappingPlan.native_plan(server_name="streamable-http-server"),
    )


def fixture_sse_transport() -> Fixture:
    return Fixture(
        name="sse_transport",
        description="Legacy SSE transport (stub compatible fixture)",
        compatible=True,
        introspection=_intro(
            "sse-server",
            [
                _tool(
                    "action",
                    "SSE action",
                    {
                        "game_id": "string",
                        "step": "integer",
                        "role": "string",
                        "phase": "string",
                        "commitment": "string",
                        "move": "string",
                        "nonces": "object",
                        "config_sha256": "string",
                    },
                )
            ],
        ),
        expected_plan=ProtocolMappingPlan.native_plan(server_name="sse-server"),
    )


def fixture_stdio() -> Fixture:

    intro = IntrospectionResult(
        server_name="stdio-fixture",
        server_version="1.0",
        protocol_version="2024-11-05",
        tools=[],
        resources=[],
        prompts=[],
        raw_capabilities={},
        schema_digest="stdio-fixture",
    )
    return Fixture(
        name="stdio_fixture",
        description="Local stdio fixture for testing",
        compatible=True,
        introspection=intro,
        expected_plan=ProtocolMappingPlan.native_plan(server_name="stdio-fixture"),
    )
