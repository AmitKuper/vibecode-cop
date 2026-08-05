"""Failure and success branches for negotiation, probes, and Gmail senders."""

from __future__ import annotations

import json

import pytest

from agent.adaptive.adapter import (
    AdaptedRequest,
    ProtocolCompatibilityError,
)
from agent.adaptive.conformance import ConformanceProbes, ConformanceReport, ProbeOutcome
from agent.adaptive.introspector import IntrospectionResult
from agent.adaptive.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    ProtocolMappingPlan,
)
from agent.adaptive.pipeline import (
    AdaptiveNegotiationResult,
    native_adapter,
    run_adaptive_negotiation,
    run_adaptive_negotiation_sync,
)
from agent.adaptive.transport_probe import ProbeResult, TransportType
from agent.gmail.sender import AcceptanceFileGmailSender, GmailApiSender


def _probe(transport=TransportType.STREAMABLE_HTTP):
    return ProbeResult(transport, "http://peer", "http://peer/mcp", 1.0, "notes")


def _intro(digest="native"):
    return IntrospectionResult("peer", "1", "p", [], [], [], {}, digest)


async def _patch_transport(monkeypatch, probe=None, intro=None):
    chosen_probe = probe or _probe()
    chosen_intro = intro or _intro()

    async def fake_probe(_self, _url):
        return chosen_probe

    async def fake_intro(_self, _probe_result):
        return chosen_intro

    monkeypatch.setattr("agent.adaptive.pipeline.TransportProbe.probe", fake_probe)
    monkeypatch.setattr("agent.adaptive.pipeline.MCPIntrospector.introspect", fake_intro)


@pytest.mark.asyncio
async def test_negotiation_success_properties_and_cache_hit(monkeypatch, tmp_path) -> None:
    await _patch_transport(monkeypatch)
    result = await run_adaptive_negotiation("http://peer", cache_dir=tmp_path)
    assert result.is_compatible
    assert result.profile_hash
    assert result.plan_hash
    assert not result.cache_hit

    cached = await run_adaptive_negotiation("http://peer", cache_dir=tmp_path)
    assert cached.cache_hit
    assert cached.profile_hash == result.profile_hash


@pytest.mark.asyncio
async def test_negotiation_rejects_unknown_transport(monkeypatch, tmp_path) -> None:
    await _patch_transport(
        monkeypatch,
        ProbeResult(TransportType.UNKNOWN, "bad", "bad", 0.0, "offline"),
    )
    with pytest.raises(ProtocolCompatibilityError, match="No compatible MCP transport"):
        await run_adaptive_negotiation("bad", cache_dir=tmp_path)


@pytest.mark.asyncio
async def test_negotiation_rejects_static_and_conformance_failures(monkeypatch, tmp_path) -> None:
    await _patch_transport(monkeypatch, intro=_intro("uncached"))
    incompatible = ProtocolMappingPlan.native_plan()
    incompatible.verdict = CompatibilityVerdict.INCOMPATIBLE
    monkeypatch.setattr(
        "agent.adaptive.pipeline.ProtocolUnderstandingAgent.create_plan",
        lambda _self, _intro_result: incompatible,
    )
    with pytest.raises(ProtocolCompatibilityError, match="Static verification failed"):
        await run_adaptive_negotiation("http://peer", cache_dir=tmp_path)

    compatible = ProtocolMappingPlan.native_plan()
    monkeypatch.setattr(
        "agent.adaptive.pipeline.ProtocolUnderstandingAgent.create_plan",
        lambda _self, _intro_result: compatible,
    )
    failed = ConformanceReport(False, [ProbeOutcome("broken", False)])
    monkeypatch.setattr("agent.adaptive.pipeline.ConformanceProbes.run_all", lambda _self: failed)
    with pytest.raises(ProtocolCompatibilityError, match="Conformance probes failed"):
        await run_adaptive_negotiation("http://peer", cache_dir=tmp_path)


def test_negotiation_sync_native_and_result_accessors(monkeypatch, tmp_path) -> None:
    async def fake_probe(_self, _url):
        return _probe()

    async def fake_intro(_self, _probe_result):
        return _intro()

    monkeypatch.setattr("agent.adaptive.pipeline.TransportProbe.probe", fake_probe)
    monkeypatch.setattr("agent.adaptive.pipeline.MCPIntrospector.introspect", fake_intro)
    sync = run_adaptive_negotiation_sync("http://peer", cache_dir=tmp_path)
    assert isinstance(sync, AdaptiveNegotiationResult)
    native = native_adapter()
    assert native.is_compatible
    assert native.adapter.per_turn_llm_calls == 0


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


def test_gmail_sender_validation_and_attachment_rejection(tmp_path) -> None:
    missing = GmailApiSender(tmp_path / "missing.json")
    with pytest.raises(RuntimeError, match="token missing"):
        missing.validate()

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")
    invalid = GmailApiSender(invalid_path)
    with pytest.raises(RuntimeError, match="neither token nor refresh_token"):
        invalid.validate()

    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({"refresh_token": "refresh"}), encoding="utf-8")
    sender = GmailApiSender(token_path)
    sender.validate()
    with pytest.raises(RuntimeError, match="untyped attachments"):
        sender("to@example.com", "subject", "body", [tmp_path / "file"])


def test_gmail_sender_calls_real_api_boundary(monkeypatch, tmp_path) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({"token": "access"}), encoding="utf-8")
    sender = GmailApiSender(token_path)
    monkeypatch.setattr(
        "agent.reports.gmail_send.load_oauth_credentials",
        lambda path: ("credentials", path),
    )

    def fake_send(message, credentials):
        assert message["To"] == "to@example.com"
        assert message["Subject"] == "subject"
        assert credentials[0] == "credentials"
        return "gmail-message-id"

    monkeypatch.setattr("agent.reports.gmail_send.gmail_api_send", fake_send)
    assert sender("to@example.com", "subject", "body", []) == "gmail-message-id"


def test_acceptance_fake_gmail_is_explicit_deterministic_outbox(tmp_path) -> None:
    outbox = tmp_path / "nested" / "outbox.jsonl"
    sender = AcceptanceFileGmailSender(outbox)
    sender.validate()
    first = sender("to@example.com", "subject", "body", ["artifact.json"])
    second = sender("to@example.com", "subject", "body", ["artifact.json"])
    records = [json.loads(line) for line in outbox.read_text(encoding="utf-8").splitlines()]
    assert first == second
    assert len(records) == 2
    assert records[0]["delivery_kind"] == "FAKE_ACCEPTANCE_ONLY"
    assert records[0]["attachments"] == ["artifact.json"]
