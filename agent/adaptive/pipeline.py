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

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agent.adaptive.adapter import DeterministicProtocolAdapter, ProtocolCompatibilityError
from agent.adaptive.conformance import ConformanceProbes
from agent.adaptive.introspector import MCPIntrospector
from agent.adaptive.mapping_plan import ProtocolMappingPlan
from agent.adaptive.profile import ProfileCache, ProtocolProfile
from agent.adaptive.protocol_agent import ProtocolUnderstandingAgent
from agent.adaptive.reference_v3 import (
    ReferenceV3Profile,
    ReferenceV3Session,
    assert_core_vectors,
)
from agent.adaptive.transport_probe import TransportProbe, TransportType
from agent.adaptive.verifier import StaticSemanticVerifier

logger = logging.getLogger(__name__)


async def discover_reference_v3(
    opponent_url: str,
    *,
    probe_timeout_s: float = 5.0,
    introspect_timeout_s: float = 10.0,
    tool_caller: Callable[[str, dict], Awaitable[dict]] | None = None,
) -> tuple[ReferenceV3Profile, ReferenceV3Session]:
    """Discover and lock the league kit's distinct push-only protocol.

    The generic eight-phase adapter must not flatten this dialect: its move and nonce are both
    deferred to the final audit.  This entry point still uses the same transport probe and full
    MCP introspection, but binds an exact four-tool surface, reproduces the published CORE
    vectors, and returns a deterministic queue/session implementation for gameplay.
    """
    probe = await TransportProbe(timeout_s=probe_timeout_s).probe(opponent_url)
    if probe.transport == TransportType.UNKNOWN:
        raise ProtocolCompatibilityError(
            f"No compatible MCP transport found at {opponent_url}: {probe.probe_notes}"
        )
    intro = await MCPIntrospector(timeout_s=introspect_timeout_s).introspect(probe)
    try:
        profile = ReferenceV3Profile.from_introspection(intro)
        assert_core_vectors()
    except ValueError as exc:
        raise ProtocolCompatibilityError(
            f"reference-v3 discovery failed before first commitment: {exc}"
        ) from exc
    caller = tool_caller or _discovered_tool_caller(probe)
    return profile, ReferenceV3Session(caller)


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


async def _verify_conformance(
    adapter: DeterministicProtocolAdapter,
    plan: ProtocolMappingPlan,
    probe,
    tool_caller: Callable[[str, dict], Awaitable[dict]] | None,
):
    probes = ConformanceProbes(adapter, plan)
    local = probes.run_all()
    if not local.all_passed:
        raise ProtocolCompatibilityError(f"Conformance probes failed: {local.failed_probes()}")
    if probe.transport != TransportType.STDIO or tool_caller is not None or probe.stdio_command:
        caller = tool_caller or _discovered_tool_caller(probe)
        remote = await probes.run_remote(caller)
        if not remote.all_passed:
            raise ProtocolCompatibilityError(
                f"Remote conformance probes failed: {remote.failed_probes()}"
            )
        local.probes.extend(remote.probes)
    return local


def _discovered_tool_caller(probe):
    """Build a caller for the transport that was actually negotiated."""
    from fastmcp import Client
    from fastmcp.client.transports import SSETransport, StreamableHttpTransport

    if probe.transport == TransportType.SSE:
        transport = SSETransport(probe.mcp_endpoint)
    elif probe.transport == TransportType.STREAMABLE_HTTP:
        transport = StreamableHttpTransport(probe.mcp_endpoint)
    elif probe.transport == TransportType.STDIO and probe.stdio_command:
        from fastmcp.client.transports import StdioTransport

        transport = StdioTransport(probe.stdio_command[0], list(probe.stdio_command[1:]))
    else:
        raise ProtocolCompatibilityError(f"No remote caller for {probe.transport}")

    async def call(tool_name: str, params: dict) -> dict:
        async with Client(transport) as client:
            result = await client.call_tool(tool_name, params)
        if not result.content:
            return {"ok": getattr(result, "is_error", False) is not True}
        item = result.content[0]
        value = item.text if hasattr(item, "text") else str(item)
        if getattr(result, "is_error", False) is True:
            return {"ok": False, "error": value}
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {"ok": True, "raw": value}
        return parsed if isinstance(parsed, dict) else {"ok": True, "raw": parsed}

    return call


def run_adaptive_negotiation_sync(
    opponent_url: str,
    llm: Any = None,
    cache_dir: Path | None = None,
) -> AdaptiveNegotiationResult:
    """Synchronous wrapper for run_adaptive_negotiation."""
    return asyncio.run(run_adaptive_negotiation(opponent_url, llm=llm, cache_dir=cache_dir))


def native_adapter() -> AdaptiveNegotiationResult:
    """Return an identity adapter for a native canonical server."""
    plan = ProtocolMappingPlan.native_plan()
    profile = ProtocolProfile.native()
    adapter = DeterministicProtocolAdapter(plan)
    return AdaptiveNegotiationResult(profile, adapter)


async def verify_locked_schema(profile: ProtocolProfile, timeout_s: float = 10.0) -> None:
    """Re-introspect without an LLM and abort if a locked peer schema changed."""
    from agent.adaptive.transport_probe import ProbeResult

    probe = ProbeResult(
        transport=TransportType(profile.remote_transport),
        base_url=profile.remote_endpoint,
        mcp_endpoint=profile.remote_endpoint,
        latency_ms=0.0,
        probe_notes="locked-profile recheck",
        stdio_command=profile.remote_stdio_command,
    )
    current = await MCPIntrospector(timeout_s=timeout_s).introspect(probe)
    if current.schema_digest != profile.remote_schema_digest:
        raise ProtocolCompatibilityError(
            "Remote schema changed after ProtocolProfile lock: "
            f"{profile.remote_schema_digest} != {current.schema_digest}"
        )
