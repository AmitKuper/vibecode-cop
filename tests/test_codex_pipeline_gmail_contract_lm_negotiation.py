"""Failure and success branches for adaptive negotiation runs (league_manager)."""

from __future__ import annotations

import pytest

from league_manager.protocol.adapter import ProtocolCompatibilityError
from league_manager.protocol.conformance import ConformanceReport, ProbeOutcome
from league_manager.protocol.mapping_plan import CompatibilityVerdict, ProtocolMappingPlan
from league_manager.protocol.pipeline import (
    AdaptiveNegotiationResult,
    native_adapter,
    run_adaptive_negotiation,
    run_adaptive_negotiation_sync,
)
from league_manager.protocol.transport_probe import ProbeResult, TransportType
from tests.helpers_codex_pipeline_gmail_lm import (
    _conforming_probe,
    _intro,
    _patch_transport,
    _probe,
)


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
        "league_manager.protocol.pipeline.ProtocolUnderstandingAgent.create_plan",
        lambda _self, _intro_result: incompatible,
    )
    with pytest.raises(ProtocolCompatibilityError, match="Static verification failed"):
        await run_adaptive_negotiation("http://peer", cache_dir=tmp_path)

    compatible = ProtocolMappingPlan.native_plan()
    monkeypatch.setattr(
        "league_manager.protocol.pipeline.ProtocolUnderstandingAgent.create_plan",
        lambda _self, _intro_result: compatible,
    )
    failed = ConformanceReport(False, [ProbeOutcome("broken", False)])
    monkeypatch.setattr(
        "league_manager.protocol.pipeline.ConformanceProbes.run_all", lambda _self: failed
    )
    with pytest.raises(ProtocolCompatibilityError, match="Conformance probes failed"):
        await run_adaptive_negotiation("http://peer", cache_dir=tmp_path)


def test_negotiation_sync_native_and_result_accessors(monkeypatch, tmp_path) -> None:
    async def fake_probe(_self, _url):
        return _probe()

    async def fake_intro(_self, _probe_result):
        return _intro()

    monkeypatch.setattr("league_manager.protocol.pipeline.TransportProbe.probe", fake_probe)
    monkeypatch.setattr("league_manager.protocol.pipeline.MCPIntrospector.introspect", fake_intro)

    monkeypatch.setattr(
        "league_manager.protocol.pipeline._discovered_tool_caller", lambda _probe: _conforming_probe
    )
    sync = run_adaptive_negotiation_sync("http://peer", cache_dir=tmp_path)
    assert isinstance(sync, AdaptiveNegotiationResult)
    native = native_adapter()
    assert native.is_compatible
    assert native.adapter.per_turn_llm_calls == 0
