"""Regression tests for bounded adaptive transport handshakes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sse_probe_accepts_streaming_handshake_without_reading_body() -> None:
    from agent.adaptive.transport_probe import TransportType, _try_sse

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream; charset=utf-8"},
    )
    stream = MagicMock()
    stream.__aenter__ = AsyncMock(return_value=response)
    stream.__aexit__ = AsyncMock(return_value=None)
    client.stream.return_value = stream

    with patch("agent.adaptive.transport_probe.httpx.AsyncClient", return_value=client):
        result = await _try_sse("http://peer.example", 0.5)

    assert result is not None
    assert result.transport is TransportType.SSE
    client.stream.assert_called_once()


def test_known_signed_envelope_is_mapped_before_untrusted_llm() -> None:
    from agent.adaptive.introspector import IntrospectionResult, ToolSchema
    from agent.adaptive.protocol_agent import ProtocolUnderstandingAgent

    def schema(fields):
        return {"properties": {name: {"type": "string"} for name in fields}}

    intro = IntrospectionResult(
        server_name="course-peer",
        server_version="1.0",
        protocol_version="2025-11-25",
        tools=[
            ToolSchema("start_game", "", schema(["message_json", "signature"])),
            ToolSchema("action", "", schema(["game_id", "message_json", "signature"])),
        ],
        resources=[],
        prompts=[],
        raw_capabilities={},
        schema_digest="d" * 64,
    )
    llm = MagicMock()

    plan = ProtocolUnderstandingAgent(llm=llm).create_plan(intro)

    assert plan.agent_model == "deterministic-signed-envelope"
    llm.call.assert_not_called()
