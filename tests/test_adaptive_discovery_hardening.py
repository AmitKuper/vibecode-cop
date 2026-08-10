"""Security and end-to-end discovery contracts for adaptive MCP."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest

from cop_worker.mcp.client import GameMCPClient
from cop_worker.protocol.adapter import DeterministicProtocolAdapter
from cop_worker.protocol.conformance import ConformanceProbes
from cop_worker.protocol.fixtures import (
    all_compatible_fixtures,
    fixture_nested_envelope,
)
from cop_worker.protocol.introspector import IntrospectionResult, MCPIntrospector
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan
from cop_worker.protocol.pipeline import (
    _discovered_tool_caller,
    run_adaptive_negotiation,
    verify_locked_schema,
)
from cop_worker.protocol.profile import ProtocolProfile
from cop_worker.protocol.protocol_agent import ProtocolUnderstandingAgent
from cop_worker.protocol.transport_probe import ProbeResult, TransportType, normalize_mcp_base_url

_DISCOVERY_FIXTURES = [
    fixture for fixture in all_compatible_fixtures() if fixture.name != "stdio_fixture"
]


@pytest.mark.parametrize("fixture", _DISCOVERY_FIXTURES, ids=lambda item: item.name)
def test_compatible_fixtures_are_discovered_not_preapproved(fixture) -> None:
    plan = ProtocolUnderstandingAgent().create_plan(fixture.introspection)
    assert plan.is_compatible(), plan.capability_gaps
    assert plan.remote_schema_digest == fixture.introspection.schema_digest
    assert plan.has_required_phases()
    assert ConformanceProbes(DeterministicProtocolAdapter(plan), plan).run_all().all_passed


def test_structured_agent_plan_supports_nested_split_mapping_and_rejects_invention() -> None:
    fixture = fixture_nested_envelope()
    payload = fixture.expected_plan.to_dict()
    plan = ProtocolUnderstandingAgent(model_id="fixture-agent")._build_plan_from_llm(
        payload,
        fixture.introspection,
    )
    assert plan.agent_model == "fixture-agent"
    commit = next(item for item in plan.phase_mappings if item.phase == "commit")
    assert any(field.remote_field == "body.commitment" for field in commit.field_mappings)

    invented = deepcopy(payload)
    invented["phase_mappings"][0]["remote_tool"] = "unadvertised_tool"
    with pytest.raises(ValueError, match="unknown remote tool"):
        ProtocolUnderstandingAgent()._build_plan_from_llm(invented, fixture.introspection)


@pytest.mark.asyncio
async def test_remote_conformance_requires_stable_rejection() -> None:
    plan = ProtocolMappingPlan.native_plan()
    probes = ConformanceProbes(DeterministicProtocolAdapter(plan), plan)
    observed = []

    async def conform(tool_name, params):
        observed.append((tool_name, params))
        if tool_name == plan.conformance_tool:
            return {
                "ok": True,
                "game_id": params["game_id"],
                "phase": params["phase"],
                "idempotent": True,
                "side_effects": 0,
                "canonical_order": True,
                "canonical_json_bytes": True,
                "commitment_binding": True,
                "nonce_final_audit_only": True,
                "comprehensive_audit": True,
                "result_agreement": True,
            }
        return {
            "ok": False,
            "error": "invalid probe signature",
            "game_id": params["game_id"],
            "phase": params["phase"],
        }

    passed = await probes.run_remote(conform)
    assert passed.all_passed
    assert len(observed) == 4 * len(ProtocolMappingPlan.REQUIRED_PHASES)
    assert "private_key" not in str(observed)

    async def reject_only(_tool_name, params):
        return {
            "ok": False,
            "error": "invalid probe signature",
            "game_id": params.get("game_id"),
            "phase": params.get("phase"),
        }

    reject_only_report = await probes.run_remote(reject_only)
    assert not reject_only_report.all_passed
    assert len(reject_only_report.failed_probes()) == len(ProtocolMappingPlan.REQUIRED_PHASES)

    async def unsafe_accept(_tool_name, _params):
        return {"ok": True}

    failed = await probes.run_remote(unsafe_accept)
    assert not failed.all_passed
    assert len(failed.failed_probes()) == len(ProtocolMappingPlan.REQUIRED_PHASES)


def test_profile_hash_covers_every_mapping_detail() -> None:
    profile = ProtocolProfile.native()
    assert profile.verify_integrity()
    data = profile.to_dict()
    data["mapping_plan"]["phase_mappings"][0]["field_mappings"][0]["remote_field"] = "tampered"
    restored = ProtocolProfile.from_dict(data)
    assert not restored.verify_integrity()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://team.com/mcp", "https://team.com"),
        ("https://team.com/sse/", "https://team.com"),
        ("https://team.example/custom/mcp", "https://team.example/custom"),
        ("https://team.example/custom", "https://team.example/custom"),
    ],
)
def test_endpoint_normalization_removes_only_exact_transport_suffix(value, expected) -> None:
    assert normalize_mcp_base_url(value) == expected


def test_game_client_uses_discovered_transport() -> None:
    client = GameMCPClient("https://team.com/mcp", "test-secret")
    assert client._transport.url == "https://team.com/sse"
    client.configure_transport("streamable_http", "https://team.com/mcp")
    assert client._transport.url == "https://team.com/mcp"
    client.configure_transport("sse", "https://team.com/sse")
    assert client._transport.url == "https://team.com/sse"
    with pytest.raises(ValueError, match="Unsupported"):
        client.configure_transport("stdio", "stdio")


@pytest.mark.asyncio
async def test_locked_schema_recheck_rejects_mid_series_change(monkeypatch) -> None:
    profile = ProtocolProfile.native()

    async def changed(_self, _probe):
        return IntrospectionResult("peer", "1", "p", [], [], [], {}, "changed")

    monkeypatch.setattr("cop_worker.protocol.pipeline.MCPIntrospector.introspect", changed)
    with pytest.raises(Exception, match="schema changed"):
        await verify_locked_schema(profile)


@pytest.mark.asyncio
async def test_stdio_transport_introspects_a_real_fixture_process(tmp_path) -> None:
    script = tmp_path / "stdio_peer.py"
    script.write_text(
        "from fastmcp import FastMCP\n"
        "mcp = FastMCP('stdio-peer')\n"
        "@mcp.tool\n"
        "def action(game_id: str, role: str, phase: str) -> dict:\n"
        "    return {'ok': False, 'error': 'probe'}\n"
        "if __name__ == '__main__':\n"
        "    mcp.run()\n",
        encoding="utf-8",
    )
    probe = ProbeResult(
        TransportType.STDIO,
        "stdio",
        "stdio",
        0.0,
        "fixture",
        (sys.executable, str(script)),
    )
    result = await MCPIntrospector(timeout_s=15).introspect(probe)
    assert result.tool_names() == ["action"]


@pytest.mark.asyncio
async def test_full_stdio_discovery_conformance_and_profile_lock(tmp_path) -> None:
    script = tmp_path / "stdio_signed_peer.py"
    script.write_text(
        "from fastmcp import FastMCP\n"
        "import json\n"
        "mcp = FastMCP('stdio-signed-peer')\n"
        "@mcp.tool\n"
        "def start_game(message_json: str, signature: str) -> dict:\n"
        "    body = json.loads(message_json)\n"
        "    return {'ok': False, 'error': 'invalid probe signature',\n"
        "            'game_id': body['game_id'], 'phase': 'start_game'}\n"
        "@mcp.tool\n"
        "def action(game_id: str, message_json: str, signature: str) -> dict:\n"
        "    body = json.loads(message_json)\n"
        "    return {'ok': False, 'error': 'invalid probe signature',\n"
        "            'game_id': game_id, 'phase': body['phase']}\n"
        "@mcp.tool\n"
        "def protocol_conformance(phase: str, game_id: str, request_digest: str,\n"
        "                         idempotency_key: str) -> dict:\n"
        "    return {'ok': True, 'game_id': game_id, 'phase': phase,\n"
        "            'idempotent': True, 'side_effects': 0,\n"
        "            'canonical_order': True, 'canonical_json_bytes': True,\n"
        "            'commitment_binding': True, 'nonce_final_audit_only': True,\n"
        "            'comprehensive_audit': True, 'result_agreement': True}\n"
        "if __name__ == '__main__':\n"
        "    mcp.run()\n",
        encoding="utf-8",
    )
    result = await run_adaptive_negotiation(
        f'stdio://"{sys.executable}" "{script}"',
        cache_dir=tmp_path / "profiles",
        introspect_timeout_s=15,
    )
    assert result.is_compatible
    assert result.profile.remote_transport == "stdio"
    assert result.profile.remote_stdio_command == (sys.executable, str(script))
    assert result.profile.verify_integrity()
    client = GameMCPClient("http://unused.example/mcp", "secret")
    client.configure_transport("stdio", "stdio", result.profile.remote_stdio_command)
    assert type(client._transport).__name__ == "StdioTransport"


def test_protocol_agent_parsing_and_legacy_mapping_fail_closed() -> None:
    intro = fixture_nested_envelope().introspection
    agent = ProtocolUnderstandingAgent(model_id="test-model")
    payload = {"verdict": "INCOMPATIBLE", "capability_gaps": ["probe"]}
    assert agent._parse_llm_response(json.dumps(payload)) == payload
    assert agent._parse_llm_response(f"prefix {json.dumps(payload)} suffix") == payload
    with pytest.raises(ValueError, match="valid JSON"):
        agent._parse_llm_response("not-json")

    legacy = agent._build_plan_from_llm(
        {
            "remote_tool_name": "missing-name",
            "verdict": "INCOMPATIBLE",
            "field_renames": {"game_id": "meta"},
            "capability_gaps": ["legacy mapping is not proven"],
        },
        intro,
    )
    assert legacy.remote_tool_name == intro.tools[0].name
    assert legacy.verdict.value == "INCOMPATIBLE"
    assert agent._closest_match("move", {"move_commitment": {}}) is None
    assert agent._closest_match("move", {"move": {}}) == "move"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "is_error", "expected"),
    [
        ([], False, {"ok": True}),
        ([SimpleNamespace(text="bad")], True, {"ok": False, "error": "bad"}),
        ([SimpleNamespace(text="not-json")], False, {"ok": True, "raw": "not-json"}),
        ([SimpleNamespace(text="[1,2]")], False, {"ok": True, "raw": [1, 2]}),
        ([SimpleNamespace(text='{"ok":false}')], False, {"ok": False}),
    ],
)
async def test_discovered_caller_normalizes_result_shapes(monkeypatch, content, is_error, expected):
    class FakeClient:
        def __init__(self, _transport):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def call_tool(self, _tool, _params):
            return SimpleNamespace(content=content, is_error=is_error)

    monkeypatch.setattr("fastmcp.Client", FakeClient)
    probe = ProbeResult(TransportType.SSE, "http://peer", "http://peer/sse", 0.0, "test")
    assert await _discovered_tool_caller(probe)("action", {}) == expected


def test_discovered_caller_supports_streamable_stdio_and_rejects_unknown() -> None:
    streamable = ProbeResult(
        TransportType.STREAMABLE_HTTP, "http://peer", "http://peer/mcp", 0.0, "test"
    )
    stdio = ProbeResult(
        TransportType.STDIO, "stdio", "stdio", 0.0, "test", (sys.executable, "peer.py")
    )
    assert callable(_discovered_tool_caller(streamable))
    assert callable(_discovered_tool_caller(stdio))
    with pytest.raises(Exception, match="No remote caller"):
        _discovered_tool_caller(
            ProbeResult(TransportType.UNKNOWN, "unknown", "unknown", 0.0, "test")
        )
