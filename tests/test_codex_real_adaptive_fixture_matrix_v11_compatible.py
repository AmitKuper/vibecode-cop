"""Real-process adaptive MCP matrix required by the v11 contract — compatible variants."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp import Client

from cop_worker.protocol.adapter import DeterministicProtocolAdapter
from cop_worker.protocol.conformance import ConformanceProbes
from cop_worker.protocol.introspector import MCPIntrospector
from cop_worker.protocol.profile import ProtocolProfile
from cop_worker.protocol.protocol_agent import ProtocolUnderstandingAgent
from cop_worker.protocol.transport_probe import ProbeResult
from cop_worker.protocol.verifier import StaticSemanticVerifier
from tests.helpers_adaptive_fixture_matrix import _fixture_probe, _result_dict, _transport

COMPATIBLE = (
    ("native", "stdio"),
    ("split", "stdio"),
    ("renamed", "stdio"),
    ("nested", "stdio"),
    ("packed", "stdio"),
    ("enum_aliases", "stdio"),
    ("optional_extra", "stdio"),
    ("nested_response", "stdio"),
    ("streamable_http", "http"),
    ("sse", "sse"),
)


def _canonical(phase: str, gamelet: int, *, game_id: str | None = None) -> dict:
    value = {
        "game_id": game_id or f"FIXTURE_GAME_{gamelet}",
        "gamelet": gamelet,
        "step": 1,
        "role": "cop",
        "phase": phase,
        "config_sha256": "c" * 64,
        "timestamp": "2026-08-06T00:00:00Z",
        "signature": "fixture-valid",
        "commitment": "d" * 64,
        "hint": "A bounded fixture message.",
        "move": "N",
        "nonces": {"1": "fixture-nonce"},
        "signed_audit_summary": {"signature": "fixture-valid"},
        "result_hash": "e" * 64,
        "signed_agreement": {"signature": "fixture-valid"},
        "reason": "fixture-complete",
    }
    value["message_json"] = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


async def _exercise_compatible(probe: ProbeResult) -> tuple[int, ProtocolProfile]:
    intro = await MCPIntrospector(timeout_s=15).introspect(probe)
    plan = ProtocolUnderstandingAgent().create_plan(intro)
    verification = StaticSemanticVerifier().verify(plan)
    assert verification.passed, verification.errors
    adapter = DeterministicProtocolAdapter(plan)
    profile = ProtocolProfile.build(probe, plan)
    assert profile.verify_integrity(intro.schema_digest)

    accepted = 0
    async with Client(_transport(probe)) as client:

        async def call(tool_name: str, params: dict) -> dict:
            return _result_dict(await client.call_tool(tool_name, params))

        conformance = await ConformanceProbes(adapter, plan).run_remote(call)
        assert conformance.all_passed, conformance.failed_probes()
        for gamelet in range(1, 7):
            for phase in (
                "start_game",
                "commit",
                "reveal",
                "final_audit",
                "audit_summary",
                "game_end",
            ):
                canonical = _canonical(phase, gamelet)
                request = adapter.adapt_request(phase, canonical)
                response = await call(request.tool_name, request.params)
                adapted = adapter.adapt_response(
                    phase, response, {"game_id": canonical["game_id"], "phase": phase}
                )
                assert adapted.extracted["ok"] is True
                accepted += 1
        canonical = _canonical("result_agreement", 6, game_id="FIXTURE_SERIES")
        request = adapter.adapt_request("result_agreement", canonical)
        response = await call(request.tool_name, request.params)
        adapted = adapter.adapt_response(
            "result_agreement",
            response,
            {"game_id": "FIXTURE_SERIES", "phase": "result_agreement"},
        )
        assert adapted.extracted["ok"] is True
        accepted += 1

    assert adapter.per_turn_llm_calls == 0
    return accepted, profile


@pytest.mark.parametrize(("variant", "transport"), COMPATIBLE)
def test_actual_compatible_mcp_process_completes_six_gamelets(variant: str, transport: str) -> None:
    with _fixture_probe(variant, transport) as probe:
        accepted, profile = asyncio.run(_exercise_compatible(probe))
    assert accepted == 37
    assert profile.remote_transport in {"stdio", "streamable_http", "sse"}
