"""Behavioral tests for ProtocolUnderstandingAgent in both package trees (no LLM/network)."""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture(params=["cop_worker", "league_manager"])
def mods(request):
    pkg = request.param
    return (
        importlib.import_module(f"{pkg}.protocol.protocol_agent"),
        importlib.import_module(f"{pkg}.protocol.fixtures"),
        importlib.import_module(f"{pkg}.protocol.mapping_plan"),
    )


class _LLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def call(self, messages):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _signed_intro(fixtures, with_start=True):
    specs = [("action", {"game_id": "string", "message_json": "string", "signature": "string"})]
    if with_start:
        specs.append(("start_game", {"message_json": "string", "signature": "string"}))
    specs.append(("protocol_conformance", {"phase": "string", "game_id": "string"}))
    descriptions = {"protocol_conformance": "Side-effect-free protocol conformance probe"}
    tools = [
        fixtures._tool(name, descriptions.get(name, f"Signed {name} tool"), props)
        for name, props in specs
    ]
    return fixtures._intro("signed-server", tools)


def test_deterministic_verdicts(mods):
    agent_mod, fixtures, plan_mod = mods
    agent = agent_mod.ProtocolUnderstandingAgent()
    empty = agent.create_plan(fixtures._intro("empty", []))
    assert empty.verdict == plan_mod.CompatibilityVerdict.INCOMPATIBLE
    assert empty.capability_gaps == ["no MCP tools discovered"]
    signed = agent.create_plan(_signed_intro(fixtures))
    assert signed.agent_model == "deterministic-signed-envelope"
    assert signed.conformance_tool == "protocol_conformance" and signed.is_compatible()
    llm = _LLM("should never be called")
    native = agent_mod.ProtocolUnderstandingAgent(llm=llm).create_plan(
        fixtures.fixture_native_action().introspection
    )
    assert native.is_compatible() and llm.calls == 0


def test_llm_fallback_and_failure_paths(mods):
    agent_mod, fixtures, _ = mods
    intro = fixtures.fixture_incompat_no_commitment().introspection
    reply = json.dumps({"verdict": "COMPATIBLE", "remote_tool_name": "action", "confidence": 0.8})
    agent = agent_mod.ProtocolUnderstandingAgent(llm=_LLM(reply), model_id="test-model")
    plan = agent.create_plan(intro)
    assert plan.remote_tool_name == "action" and plan.agent_model == "test-model"
    assert plan.confidence == 0.8
    for llm in (_LLM(RuntimeError("api down")), _LLM("not json at all")):
        fallback = agent_mod.ProtocolUnderstandingAgent(llm=llm).create_plan(intro)
        assert not fallback.is_compatible()


def test_parse_llm_response_variants(mods):
    agent_mod, _, _ = mods
    agent = agent_mod.ProtocolUnderstandingAgent()
    assert agent._parse_llm_response('{"a": 1}') == {"a": 1}
    assert agent._parse_llm_response('prose then {"a": 2} more prose') == {"a": 2}
    with pytest.raises(ValueError, match="valid JSON"):
        agent._parse_llm_response("no braces here")


def test_llm_phase_mappings_path_validated(mods):
    agent_mod, fixtures, _ = mods
    intro = _signed_intro(fixtures, with_start=False)
    reply = json.dumps(
        {
            "verdict": "COMPATIBLE",
            "remote_tool_name": "action",
            "conformance_tool": "protocol_conformance",
            "phase_mappings": [
                {
                    "phase": "commit",
                    "remote_tool": "action",
                    "field_mappings": [{"canonical_field": "game_id", "remote_field": "game_id"}],
                    "response_extraction": {"ok": "ok"},
                }
            ],
        }
    )
    agent = agent_mod.ProtocolUnderstandingAgent(llm=_LLM(reply), model_id="m2")
    plan = agent._llm_plan(intro)
    assert plan.agent_version == "2.0" and plan.phase_mappings[0].phase == "commit"


def test_validate_remote_plan_rejections(mods):
    agent_mod, fixtures, plan_mod = mods
    intro = _signed_intro(fixtures)
    agent = agent_mod.ProtocolUnderstandingAgent()

    def _plan():
        return plan_mod.ProtocolMappingPlan.signed_envelope_plan(
            schema_digest=intro.schema_digest, server_name="signed-server"
        )

    agent._validate_remote_plan(_plan(), intro)
    bad_conf = _plan()
    bad_conf.conformance_tool = "missing_tool"
    with pytest.raises(ValueError, match="unknown conformance tool"):
        agent._validate_remote_plan(bad_conf, intro)
    bad_tool = _plan()
    bad_tool.phase_mappings[0].remote_tool = "not_a_tool"
    with pytest.raises(ValueError, match="unknown remote tool"):
        agent._validate_remote_plan(bad_tool, intro)
    bad_field = _plan()
    bad_field.phase_mappings[1].field_mappings[0].remote_field = "ghost.path"
    with pytest.raises(ValueError, match="unknown field"):
        agent._validate_remote_plan(bad_field, intro)


def test_field_mapping_helpers(mods):
    agent_mod, fixtures, plan_mod = mods
    agent = agent_mod.ProtocolUnderstandingAgent()
    props = {"game_id": {}, "commitment": {}, "hint": {}, "timestamp": {}}
    by_name = {fm.canonical_field: fm for fm in agent._map_canonical_fields("commit", props)}
    assert by_name["commitment"].required and not by_name["timestamp"].required
    assert agent._closest_match("move", {"move_commitment": {}}) is None
    assert agent._closest_match("move", {"move": {}}) == "move"
    for phase in sorted(plan_mod.ProtocolMappingPlan.REQUIRED_PHASES):
        assert "game_id" in agent._canonical_fields_for_phase(phase)
        assert agent._map_canonical_fields(phase, {}) == []
    fallback = agent._build_plan_from_llm({}, fixtures._intro("empty", []))
    assert fallback.remote_tool_name == "action"
