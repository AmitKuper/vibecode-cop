"""run_adaptive_negotiation: orchestrates the full pre-game adaptive MCP pipeline.

Flow:
  TransportProbe → MCPIntrospector → ProtocolUnderstandingAgent (LLM, ONCE)
  → ProtocolMappingPlan → StaticSemanticVerifier
  → ConformanceProbes → ProtocolProfile (signed + cached)
  → DeterministicProtocolAdapter (used during gameplay, no LLM)

Raises ProtocolCompatibilityError if adaptation fails. No counted commitment
may occur until this function returns successfully.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from cop_worker.protocol.adapter import DeterministicProtocolAdapter, ProtocolCompatibilityError
from cop_worker.protocol.introspector import MCPIntrospector
from cop_worker.protocol.profile import ProfileCache, ProtocolProfile
from cop_worker.protocol.protocol_agent import ProtocolUnderstandingAgent
from cop_worker.protocol.transport_probe import TransportProbe, TransportType
from cop_worker.protocol.verifier import StaticSemanticVerifier

logger = logging.getLogger(__name__)


class AdaptiveNegotiationResult:
    def __init__(
        self,
        profile: ProtocolProfile,
        adapter: DeterministicProtocolAdapter,
        cache_hit: bool = False,
    ) -> None:
        self.profile = profile
        self.adapter = adapter
        self.cache_hit = cache_hit

    @property
    def profile_hash(self) -> str:
        return self.profile.profile_hash

    @property
    def plan_hash(self) -> str:
        return self.profile.plan_hash

    @property
    def is_compatible(self) -> bool:
        return self.profile.is_compatible()


async def run_adaptive_negotiation(
    opponent_url: str,
    llm: Any = None,
    cache_dir: Path | None = None,
    probe_timeout_s: float = 5.0,
    introspect_timeout_s: float = 10.0,
    tool_caller: Callable[[str, dict], Awaitable[dict]] | None = None,
) -> AdaptiveNegotiationResult:
    """Perform full adaptive MCP negotiation. Must complete before first commitment.

    Args:
        opponent_url: remote MCP server base URL (e.g. "http://host:port")
        llm: optional LLM for ProtocolUnderstandingAgent (pre-game only)
        cache_dir: optional directory for caching profiles by schema digest
        probe_timeout_s: transport probe deadline
        introspect_timeout_s: introspection deadline

    Returns AdaptiveNegotiationResult with profile + adapter ready for gameplay.

    Raises ProtocolCompatibilityError if the remote protocol is incompatible.
    """
    cache = ProfileCache(cache_dir)

    # Step 1: Probe transport
    logger.info("[AdaptiveMCP] Probing transport at %s", opponent_url)
    probe = await TransportProbe(timeout_s=probe_timeout_s).probe(opponent_url)
    if probe.transport == TransportType.UNKNOWN:
        raise ProtocolCompatibilityError(
            f"No compatible MCP transport found at {opponent_url}: {probe.probe_notes}"
        )

    # Step 2: Introspect remote server
    logger.info("[AdaptiveMCP] Introspecting remote tools at %s", probe.mcp_endpoint)
    intro = await MCPIntrospector(timeout_s=introspect_timeout_s).introspect(probe)
    logger.info(
        "[AdaptiveMCP] Found %d tools, schema_digest=%s", len(intro.tools), intro.schema_digest
    )

    # Step 3: Check cache by schema digest
    cached_profile = cache.get(intro.schema_digest)
    if cached_profile is not None:
        logger.info("[AdaptiveMCP] Cache hit for schema_digest=%s", intro.schema_digest)
        cached_verification = StaticSemanticVerifier().verify(cached_profile.mapping_plan)
        if not cached_verification.passed:
            cache.invalidate(intro.schema_digest)
            raise ProtocolCompatibilityError(
                "Cached profile failed current semantic verification: "
                f"{cached_verification.reject_reason()}"
            )
        adapter = DeterministicProtocolAdapter(cached_profile.mapping_plan)
        await _verify_conformance(
            adapter,
            cached_profile.mapping_plan,
            probe,
            tool_caller,
        )
        return AdaptiveNegotiationResult(cached_profile, adapter, cache_hit=True)

    # Step 4: Run ProtocolUnderstandingAgent (LLM, ONCE, pre-game only)
    logger.info("[AdaptiveMCP] Running ProtocolUnderstandingAgent")
    model_id = getattr(llm, "model", "unknown") if llm else "heuristic"
    agent = ProtocolUnderstandingAgent(llm=llm, model_id=model_id)
    plan = agent.create_plan(intro)
    logger.info(
        "[AdaptiveMCP] Plan: verdict=%s confidence=%.2f gaps=%s",
        plan.verdict.value,
        plan.confidence,
        plan.capability_gaps,
    )

    # Step 5: Static semantic verification
    verifier = StaticSemanticVerifier()
    verification = verifier.verify(plan)
    if not verification.passed:
        raise ProtocolCompatibilityError(
            f"Static verification failed before first commitment: {verification.reject_reason()}"
        )

    # Step 6: Build adapter and run conformance probes
    adapter = DeterministicProtocolAdapter(plan)
    conformance = await _verify_conformance(adapter, plan, probe, tool_caller)

    # Step 7: Build and cache the ProtocolProfile
    profile = ProtocolProfile.build(probe, plan)
    profile.compatible_fixtures_passed = [p.probe_name for p in conformance.probes if p.passed]
    cache.put(profile)

    logger.info(
        "[AdaptiveMCP] Negotiation complete: profile_hash=%s transport=%s",
        profile.profile_hash,
        profile.remote_transport,
    )
    return AdaptiveNegotiationResult(profile, adapter)


from cop_worker.protocol.conformance import ConformanceProbes  # noqa: E402,F401  (re-export)
from cop_worker.protocol.pipeline_discovery import (  # noqa: E402,F401  (re-exports)
    _verify_conformance,
    discover_reference_v3,
)
from cop_worker.protocol.pipeline_helpers import (  # noqa: E402,F401  (re-exports)
    _discovered_tool_caller,
    native_adapter,
    run_adaptive_negotiation_sync,
    verify_locked_schema,
)
