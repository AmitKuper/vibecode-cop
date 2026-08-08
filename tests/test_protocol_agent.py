"""Fast unit tests for the ProtocolUnderstandingAgent (both package copies).

create_plan() is synchronous and consumes an IntrospectionResult — the
acceptance fixtures provide those, so no network / no LLM is needed.
"""

from __future__ import annotations

import pytest

from cop_worker.protocol import fixtures as cop_fx
from cop_worker.protocol import introspector as cop_intro
from cop_worker.protocol import protocol_agent as cop_pa
from league_manager.protocol import fixtures as lm_fx
from league_manager.protocol import introspector as lm_intro
from league_manager.protocol import protocol_agent as lm_pa

PKGS = [(cop_fx, cop_intro, cop_pa), (lm_fx, lm_intro, lm_pa)]


def _empty_intro(intro_mod):
    return intro_mod.IntrospectionResult(
        server_name="srv", server_version="1.0", protocol_version="1.0",
        tools=[], resources=[], prompts=[], raw_capabilities={}, schema_digest="d0",
    )


def _signed_envelope_intro(intro_mod):
    action = intro_mod.ToolSchema(
        "action", "signed action",
        {"properties": {"game_id": {}, "message_json": {}, "signature": {}}},
    )
    start = intro_mod.ToolSchema(
        "start_game", "handshake", {"properties": {"message_json": {}, "signature": {}}}
    )
    conf = intro_mod.ToolSchema("protocol_conformance", "conformance probe", {})
    return intro_mod.IntrospectionResult(
        server_name="signed", server_version="1.0", protocol_version="1.0",
        tools=[action, start, conf], resources=[], prompts=[], raw_capabilities={},
        schema_digest="sig16",
    )


@pytest.mark.parametrize("fx,intro_mod,pa", PKGS)
def test_no_tools_is_incompatible(fx, intro_mod, pa):
    agent = pa.ProtocolUnderstandingAgent()
    plan = agent.create_plan(_empty_intro(intro_mod))
    assert not plan.is_compatible()
    assert plan.capability_gaps


@pytest.mark.parametrize("fx,intro_mod,pa", PKGS)
def test_signed_envelope_recognised_as_compatible(fx, intro_mod, pa):
    agent = pa.ProtocolUnderstandingAgent()
    plan = agent.create_plan(_signed_envelope_intro(intro_mod))
    assert plan.is_compatible()
    assert plan.conformance_tool == "protocol_conformance"


@pytest.mark.parametrize("fx,intro_mod,pa", PKGS)
def test_native_fixture_plan_is_compatible(fx, intro_mod, pa):
    agent = pa.ProtocolUnderstandingAgent()
    plan = agent.create_plan(fx.fixture_native_action().introspection)
    assert plan.is_compatible()
    assert plan.phase_mappings


@pytest.mark.parametrize("fx,intro_mod,pa", PKGS)
def test_create_plan_runs_on_every_fixture(fx, intro_mod, pa):
    agent = pa.ProtocolUnderstandingAgent()
    for fixture in fx.all_fixtures():
        plan = agent.create_plan(fixture.introspection)
        # verdict is always populated and consistent with gap presence
        assert plan.is_compatible() == (not plan.capability_gaps)
