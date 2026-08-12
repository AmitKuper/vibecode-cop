"""Real-process adaptive MCP matrix required by the v11 contract — incompatible variants."""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client

from cop_worker.protocol.adapter import DeterministicProtocolAdapter
from cop_worker.protocol.conformance import ConformanceProbes
from cop_worker.protocol.introspector import MCPIntrospector
from cop_worker.protocol.protocol_agent import ProtocolUnderstandingAgent
from cop_worker.protocol.transport_probe import ProbeResult
from cop_worker.protocol.verifier import StaticSemanticVerifier
from tests.helpers_adaptive_fixture_matrix import _fixture_probe, _result_dict, _transport

INCOMPATIBLE = (
    "nonce_in_reveal",
    "missing_commitment",
    "missing_final_result",
    "mutable_canonicalization",
    "phase_order",
    "no_idempotency",
    "prompt_injection",
    "protected_corruption",
)


@pytest.mark.parametrize("variant", INCOMPATIBLE)
def test_actual_incompatible_mcp_process_rejected_before_commit(variant: str) -> None:
    async def verify_rejected(probe: ProbeResult) -> None:
        try:
            intro = await MCPIntrospector(timeout_s=15).introspect(probe)
        except ValueError as exc:
            assert variant == "prompt_injection"
            assert "Prompt injection" in str(exc)
            return
        plan = ProtocolUnderstandingAgent().create_plan(intro)
        verification = StaticSemanticVerifier().verify(plan)
        if not verification.passed:
            return
        adapter = DeterministicProtocolAdapter(plan)
        async with Client(_transport(probe)) as client:

            async def call(tool_name: str, params: dict) -> dict:
                return _result_dict(await client.call_tool(tool_name, params))

            report = await ConformanceProbes(adapter, plan).run_remote(call)
        assert not report.all_passed, "incompatible peer reached first counted commitment"

    with _fixture_probe(variant, "stdio") as probe:
        asyncio.run(verify_rejected(probe))
