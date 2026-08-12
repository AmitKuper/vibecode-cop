"""Security and end-to-end discovery contracts for adaptive MCP: agent plans."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from cop_worker.protocol.adapter import DeterministicProtocolAdapter
from cop_worker.protocol.conformance import ConformanceProbes
from cop_worker.protocol.fixtures import (
    all_compatible_fixtures,
    fixture_nested_envelope,
)
from cop_worker.protocol.protocol_agent import ProtocolUnderstandingAgent

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
