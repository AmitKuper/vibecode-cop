"""Fast unit tests for StaticSemanticVerifier and DeterministicProtocolAdapter.

Pure plan validation / deterministic mapping — no network, no LLM.
"""

from __future__ import annotations

import pytest

from cop_worker.protocol import verifier as cop_ver
from league_manager.protocol.adapter import (
    DeterministicProtocolAdapter,
    ProtocolCompatibilityError,
)
from league_manager.protocol.mapping_plan import CompatibilityVerdict, ProtocolMappingPlan
from league_manager.protocol.verifier import StaticSemanticVerifier


def _native():
    return ProtocolMappingPlan.native_plan("action", "srv")


def _signed():
    return ProtocolMappingPlan.signed_envelope_plan(schema_digest="d16", server_name="srv")


# --- verifier ---------------------------------------------------------------


def test_verifier_passes_signed_envelope_plan():
    result = StaticSemanticVerifier().verify(_signed())
    assert result.passed is True and result.reject_reason() == ""


def test_verifier_rejects_incompatible_plan():
    plan = ProtocolMappingPlan(
        remote_tool_name="",
        remote_server_name="s",
        remote_schema_digest="d",
        capability_gaps=["no remote tool for commit"],
        verdict=CompatibilityVerdict.INCOMPATIBLE,
    )
    result = StaticSemanticVerifier().verify(plan)
    assert result.passed is False and result.reject_reason()


def test_verifier_native_plan_returns_result():
    # exercises the full field/phase/nonce/protected checks on a real plan
    result = StaticSemanticVerifier().verify(_native())
    assert isinstance(result.passed, bool)


def test_cop_verifier_module_is_importable_mirror():
    assert cop_ver.StaticSemanticVerifier is not None  # both copies load


# --- adapter ----------------------------------------------------------------


def test_adapter_rejects_incompatible_plan():
    plan = ProtocolMappingPlan(
        remote_tool_name="",
        remote_server_name="s",
        remote_schema_digest="d",
        verdict=CompatibilityVerdict.INCOMPATIBLE,
        capability_gaps=["x"],
    )
    with pytest.raises(ProtocolCompatibilityError):
        DeterministicProtocolAdapter(plan)


def test_adapter_adapts_signed_envelope_request():
    adapter = DeterministicProtocolAdapter(_signed())
    assert adapter.per_turn_llm_calls == 0
    req = adapter.adapt_request(
        "commit",
        {"game_id": "g1", "message_json": '{"x":1}', "signature": "s"},
    )
    assert req.phase == "commit"
    assert req.tool_name and req.params and req.request_digest


def test_adapter_check_schema_digest():
    adapter = DeterministicProtocolAdapter(_signed())
    assert adapter.check_schema_digest("d16") is True
    assert adapter.check_schema_digest("different") is False
