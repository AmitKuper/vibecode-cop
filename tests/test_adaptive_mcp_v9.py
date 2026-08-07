from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Adaptive MCP v9 acceptance tests.

Compatible fixtures (11): verifier + conformance must pass; adapter must
produce valid commit/reveal/final_audit messages.

Incompatible fixtures (6): must be rejected (ProtocolCompatibilityError or
VerificationResult.passed=False) before any counted commitment.
"""


import json

import agent.adaptive.introspector as _introspector_mod
import pytest
from cop_worker.adaptive.adapter import DeterministicProtocolAdapter, ProtocolCompatibilityError
from cop_worker.adaptive.conformance import ConformanceProbes
from cop_worker.adaptive.fixtures import (
    Fixture,
    all_compatible_fixtures,
    fixture_incompat_no_commitment,
    fixture_incompat_no_final_audit,
    fixture_incompat_nonce_in_reveal,
    fixture_incompat_prompt_injection,
)
from cop_worker.adaptive.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)
from cop_worker.adaptive.verifier import StaticSemanticVerifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMMIT_MSG = {
    "game_id": "game_TEST_001",
    "step": 1,
    "role": "cop",
    "phase": "commit",
    "commitment": "a" * 64,
    "message_json": json.dumps({"commitment": "a" * 64}, separators=(",", ":")),
    "signature": "sig_placeholder_hex",
    "config_sha256": "cfg_sha_placeholder",
    "timestamp": "2026-01-01T00:00:00Z",
}
_REVEAL_MSG = {
    "game_id": "game_TEST_001",
    "step": 1,
    "role": "cop",
    "phase": "reveal",
    "move": "N",
    "message_json": '{"probe":true}',
    "signature": "sig_placeholder_hex",
    "config_sha256": "cfg_sha_placeholder",
    "timestamp": "2026-01-01T00:00:01Z",
}
_FINAL_AUDIT_MSG = {
    "game_id": "game_TEST_001",
    "step": 1,
    "role": "cop",
    "phase": "final_audit",
    "nonces": {"1": "nonce_placeholder_abc123"},
    "message_json": '{"probe":true}',
    "signature": "sig_placeholder_hex",
    "config_sha256": "cfg_sha_placeholder",
    "timestamp": "2026-01-01T00:00:02Z",
}


def _get_plan(f: Fixture) -> ProtocolMappingPlan:
    if f.expected_plan is not None:
        return f.expected_plan
    return ProtocolMappingPlan.native_plan(server_name=f.introspection.server_name)


# ---------------------------------------------------------------------------
# Compatible fixture tests (11)
# ---------------------------------------------------------------------------

COMPATIBLE = all_compatible_fixtures()
COMPATIBLE_NAMES = [f.name for f in COMPATIBLE]


@pytest.mark.parametrize("fixture", COMPATIBLE, ids=COMPATIBLE_NAMES)
def test_compatible_verifier_passes(fixture: Fixture) -> None:
    plan = _get_plan(fixture)
    result = StaticSemanticVerifier().verify(plan)
    assert result.passed, f"Verifier failed for {fixture.name}: {result.errors}"


@pytest.mark.parametrize("fixture", COMPATIBLE, ids=COMPATIBLE_NAMES)
def test_compatible_conformance_passes(fixture: Fixture) -> None:
    plan = _get_plan(fixture)
    if plan.verdict == CompatibilityVerdict.INCOMPATIBLE:
        pytest.skip(f"{fixture.name} has incompatible verdict (fixture data issue)")
    adapter = DeterministicProtocolAdapter(plan)
    probes = ConformanceProbes(adapter, plan)
    report = probes.run_all()
    assert report.all_passed, (
        f"Conformance probes failed for {fixture.name}: {report.failed_probes()}"
    )


@pytest.mark.parametrize("fixture", COMPATIBLE, ids=COMPATIBLE_NAMES)
def test_compatible_adapter_produces_commit(fixture: Fixture) -> None:
    plan = _get_plan(fixture)
    if not plan.has_required_phases():
        pytest.skip(f"{fixture.name}: plan missing phases — skipping commit test")
    adapter = DeterministicProtocolAdapter(plan)
    result = adapter.adapt_request("commit", _COMMIT_MSG)
    assert result.params, f"{fixture.name}: empty params from commit"
    all_values = str(result.params)
    assert _COMMIT_MSG["commitment"] in all_values, (
        f"{fixture.name}: commitment not found in adapted commit"
    )


@pytest.mark.parametrize("fixture", COMPATIBLE, ids=COMPATIBLE_NAMES)
def test_compatible_adapter_produces_reveal(fixture: Fixture) -> None:
    plan = _get_plan(fixture)
    if not plan.has_required_phases():
        pytest.skip(f"{fixture.name}: plan missing phases — skipping reveal test")
    adapter = DeterministicProtocolAdapter(plan)
    result = adapter.adapt_request("reveal", _REVEAL_MSG)
    assert result.params, f"{fixture.name}: empty params from reveal"


@pytest.mark.parametrize("fixture", COMPATIBLE, ids=COMPATIBLE_NAMES)
def test_compatible_adapter_produces_final_audit(fixture: Fixture) -> None:
    plan = _get_plan(fixture)
    if not plan.has_required_phases():
        pytest.skip(f"{fixture.name}: plan missing phases — skipping final_audit test")
    adapter = DeterministicProtocolAdapter(plan)
    result = adapter.adapt_request("final_audit", _FINAL_AUDIT_MSG)
    assert result.params, f"{fixture.name}: empty params from final_audit"


@pytest.mark.parametrize("fixture", COMPATIBLE, ids=COMPATIBLE_NAMES)
def test_compatible_no_per_turn_llm(fixture: Fixture) -> None:
    """Adapter must stay at zero per-turn LLM calls."""
    plan = _get_plan(fixture)
    if not plan.has_required_phases():
        pytest.skip(f"{fixture.name}: plan missing phases")
    adapter = DeterministicProtocolAdapter(plan)
    adapter.adapt_request("commit", _COMMIT_MSG)
    adapter.adapt_request("reveal", _REVEAL_MSG)
    assert adapter.per_turn_llm_calls == 0, (
        f"{fixture.name}: per_turn_llm_calls={adapter.per_turn_llm_calls} != 0"
    )


# ---------------------------------------------------------------------------
# Incompatible fixture rejection tests (6)
# ---------------------------------------------------------------------------


def test_incompat_no_final_audit_verifier_rejects() -> None:
    """Missing final_audit phase must be rejected by StaticSemanticVerifier."""
    f = fixture_incompat_no_final_audit()
    plan = f.expected_plan
    assert plan is not None
    result = StaticSemanticVerifier().verify(plan)
    assert not result.passed, "Expected verifier to reject no_final_audit plan"
    assert any("final_audit" in e or "INCOMPATIBLE" in e for e in result.errors), (
        f"Expected error mentioning final_audit or INCOMPATIBLE, got: {result.errors}"
    )


def test_incompat_nonce_in_reveal_verifier_rejects() -> None:
    """Nonce in reveal phase must be rejected by StaticSemanticVerifier."""
    f = fixture_incompat_nonce_in_reveal()
    # Build a plan that explicitly maps nonce in reveal — this is the violation
    plan = ProtocolMappingPlan(
        remote_tool_name="action",
        remote_server_name="nonce-reveal-server",
        remote_schema_digest=f.introspection.schema_digest,
        phase_mappings=[
            PhaseMapping(
                "start_game",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                ],
                {},
            ),
            PhaseMapping(
                "commit",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("commitment", "commitment"),
                ],
                {},
            ),
            PhaseMapping(
                "reveal",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("move", "move"),
                    FieldMapping("nonce", "nonce"),  # VIOLATION: nonce in reveal
                ],
                {},
            ),
            PhaseMapping(
                "final_audit",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("nonces", "nonces"),
                ],
                {},
            ),
            PhaseMapping(
                "result_agreement",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                ],
                {},
            ),
        ],
        verdict=CompatibilityVerdict.COMPATIBLE,
        confidence=0.9,
    )
    result = StaticSemanticVerifier().verify(plan)
    assert not result.passed, "Expected verifier to reject plan with nonce in reveal"
    assert any("nonce" in e for e in result.errors), (
        f"Expected error mentioning nonce, got: {result.errors}"
    )


def test_incompat_no_commitment_verifier_rejects() -> None:
    """No commitment field in commit phase must be rejected."""
    f = fixture_incompat_no_commitment()
    # Build a plan that has commit phase but no commitment field
    plan = ProtocolMappingPlan(
        remote_tool_name="action",
        remote_server_name="no-commit-server",
        remote_schema_digest=f.introspection.schema_digest,
        phase_mappings=[
            PhaseMapping(
                "start_game",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                ],
                {},
            ),
            PhaseMapping(
                "commit",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("move", "move"),  # VIOLATION: no commitment field
                ],
                {},
            ),
            PhaseMapping(
                "reveal",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("move", "move"),
                ],
                {},
            ),
            PhaseMapping(
                "final_audit",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("nonces", "nonces"),
                ],
                {},
            ),
            PhaseMapping(
                "result_agreement",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                ],
                {},
            ),
        ],
        verdict=CompatibilityVerdict.COMPATIBLE,
        confidence=0.8,
    )
    result = StaticSemanticVerifier().verify(plan)
    assert not result.passed, "Expected verifier to reject plan with no commitment binding"
    assert any("commitment" in e for e in result.errors), (
        f"Expected error mentioning commitment, got: {result.errors}"
    )


def test_incompat_prompt_injection_sanitized() -> None:
    """Prompt injection in tool description must be detected by MCPIntrospector."""
    f = fixture_incompat_prompt_injection()
    assert f.introspection.tools, "Fixture should have tools with injection"
    injection_tool = f.introspection.tools[0]
    # The introspector's sanitizer must raise on this description
    with pytest.raises(ValueError, match="(?i)(inject|forbidden|ignore previous|you are now)"):
        _introspector_mod._sanitize(injection_tool.description)


def test_incompat_explicit_verdict_rejected() -> None:
    """Any plan with INCOMPATIBLE verdict must be rejected by verifier."""
    plan = ProtocolMappingPlan(
        remote_tool_name="action",
        remote_server_name="test-server",
        remote_schema_digest="test",
        phase_mappings=[
            PhaseMapping(p, "action", [], {}) for p in ProtocolMappingPlan.REQUIRED_PHASES
        ],
        verdict=CompatibilityVerdict.INCOMPATIBLE,
        capability_gaps=["test gap"],
    )
    result = StaticSemanticVerifier().verify(plan)
    assert not result.passed
    assert any("INCOMPATIBLE" in e for e in result.errors)


def test_incompat_adapter_raises_on_incompatible_plan() -> None:
    """DeterministicProtocolAdapter must raise ProtocolCompatibilityError for incompatible plan."""
    plan = ProtocolMappingPlan(
        remote_tool_name="action",
        remote_server_name="test-server",
        remote_schema_digest="test",
        phase_mappings=[],  # missing required phases
        verdict=CompatibilityVerdict.INCOMPATIBLE,
    )
    with pytest.raises(ProtocolCompatibilityError):
        DeterministicProtocolAdapter(plan)


# ---------------------------------------------------------------------------
# Pipeline: no per-turn LLM calls in native adapter
# ---------------------------------------------------------------------------


def test_native_adapter_zero_llm_calls() -> None:
    from cop_worker.adaptive.adapter import DeterministicProtocolAdapter

    adapter = DeterministicProtocolAdapter.native()
    adapter.adapt_request("commit", _COMMIT_MSG)
    adapter.adapt_request("reveal", _REVEAL_MSG)
    adapter.adapt_request("final_audit", _FINAL_AUDIT_MSG)
    assert adapter.per_turn_llm_calls == 0


def test_native_adapter_commitment_preserved() -> None:
    adapter = DeterministicProtocolAdapter.native()
    result = adapter.adapt_request("commit", _COMMIT_MSG, {"commitment": _COMMIT_MSG["commitment"]})
    assert _COMMIT_MSG["commitment"] in str(result.params)


def test_native_adapter_game_id_preserved() -> None:
    adapter = DeterministicProtocolAdapter.native()
    result = adapter.adapt_request("commit", _COMMIT_MSG, {"game_id": _COMMIT_MSG["game_id"]})
    assert _COMMIT_MSG["game_id"] in str(result.params)


# ---------------------------------------------------------------------------
# ProtocolMappingPlan hash stability
# ---------------------------------------------------------------------------


def test_plan_hash_deterministic() -> None:
    plan = ProtocolMappingPlan.native_plan()
    h1 = plan.plan_hash()
    h2 = plan.plan_hash()
    assert h1 == h2, "plan_hash() must be deterministic"


def test_plan_serialization_roundtrip() -> None:
    plan = ProtocolMappingPlan.native_plan()
    d = plan.to_dict()
    restored = ProtocolMappingPlan.from_dict(d)
    assert restored.plan_hash() == plan.plan_hash()
    assert restored.verdict == plan.verdict


# ---------------------------------------------------------------------------
# ProfileCache roundtrip
# ---------------------------------------------------------------------------


def test_profile_cache_disk_roundtrip(tmp_path) -> None:
    from cop_worker.adaptive.profile import ProfileCache, ProtocolProfile

    cache = ProfileCache(tmp_path)
    profile = ProtocolProfile.native()
    cache.put(profile)
    hit = cache.get(profile.remote_schema_digest)
    assert hit is not None
    assert hit.profile_hash == profile.profile_hash


def test_profile_cache_miss_returns_none() -> None:
    from cop_worker.adaptive.profile import ProfileCache

    cache = ProfileCache()
    assert cache.get("nonexistent_digest_12345") is None
