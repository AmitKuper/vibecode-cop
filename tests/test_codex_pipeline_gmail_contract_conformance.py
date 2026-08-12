"""Failure branches for conformance probes."""

from __future__ import annotations

from cop_worker.protocol.adapter import AdaptedRequest
from cop_worker.protocol.conformance import ConformanceProbes
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    ProtocolMappingPlan,
)


class _Adapter:
    def __init__(self, values=None, *, error=None):
        self.values = list(values or [])
        self.error = error
        self.calls = 0

    def adapt_request(self, phase, canonical, protected=None):
        self.calls += 1
        if self.error:
            raise self.error
        value = self.values.pop(0) if self.values else dict(canonical)
        return AdaptedRequest("action", value, phase, str(self.calls))


def _probes(plan=None, adapter=None):
    chosen_plan = plan or ProtocolMappingPlan.native_plan()
    return ConformanceProbes(adapter or _Adapter(), chosen_plan)


def test_conformance_schema_field_and_commitment_failure_branches() -> None:
    empty = ProtocolMappingPlan("action", "peer", "d", [], verdict=CompatibilityVerdict.COMPATIBLE)
    probes = _probes(empty)
    assert not probes._probe_schema_validation().passed
    assert not probes._probe_field_mapping_completeness().passed
    assert not probes._probe_commitment_binding().passed
    assert not probes._probe_phase_ordering().passed

    reveal_only = ProtocolMappingPlan.native_plan()
    reveal_only.phase_mappings = [p for p in reveal_only.phase_mappings if p.phase != "reveal"]
    assert "reveal" in _probes(reveal_only)._probe_field_mapping_completeness().error

    no_value = _probes(adapter=_Adapter([{}]))
    assert "missing" in no_value._probe_commitment_binding().error
    raised = _probes(adapter=_Adapter(error=RuntimeError("adapter failed")))
    assert "adapter failed" in raised._probe_commitment_binding().error


def test_conformance_nonce_protected_and_idempotency_failure_branches() -> None:
    plan = ProtocolMappingPlan.native_plan()
    commit = next(p for p in plan.phase_mappings if p.phase == "commit")
    commit.field_mappings.append(FieldMapping("nonce", "nonce"))
    assert not _probes(plan)._probe_nonce_isolation().passed

    missing_protected = _probes(adapter=_Adapter([{"unrelated": 1}]))
    assert "lost or corrupted" in missing_protected._probe_protected_field_integrity().error
    protected_error = _probes(adapter=_Adapter(error=RuntimeError("protected failed")))
    assert "protected failed" in protected_error._probe_protected_field_integrity().error

    nondeterministic = _probes(adapter=_Adapter([{"x": 1}, {"x": 2}]))
    assert "Non-deterministic" in nondeterministic._probe_idempotency_structure().error
    deterministic_error = _probes(adapter=_Adapter(error=RuntimeError("idem failed")))
    assert "idem failed" in deterministic_error._probe_idempotency_structure().error


def test_conformance_placeholder_and_run_all_exception_branches() -> None:
    empty = _probes(adapter=_Adapter([{}, {}]))
    assert "Empty params" in empty._probe_placeholder_commit_reveal().error
    leaked = _probes(adapter=_Adapter([{"value": "real_nonce"}, {"value": "private_key"}]))
    assert "Leaked protected value" in leaked._probe_placeholder_commit_reveal().error
    failed = _probes(adapter=_Adapter(error=RuntimeError("placeholder failed")))
    assert "placeholder failed" in failed._probe_placeholder_commit_reveal().error

    probes = _probes()
    probes._probe_schema_validation = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    report = probes.run_all()
    assert not report.all_passed
    assert report.failed_probes() == ["<lambda>"]
