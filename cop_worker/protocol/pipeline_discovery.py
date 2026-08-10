"""Reference-v3 fast-path discovery and conformance verification."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from cop_worker.protocol.adapter import DeterministicProtocolAdapter, ProtocolCompatibilityError
from cop_worker.protocol.introspector import MCPIntrospector
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan
from cop_worker.protocol.reference_v3 import (
    ReferenceV3Profile,
    ReferenceV3Session,
    assert_core_vectors,
)
from cop_worker.protocol.transport_probe import TransportProbe, TransportType

logger = logging.getLogger(__name__)


def _tool_caller(probe):
    # Resolved through the pipeline module at call time so monkeypatches on
    # ``cop_worker.protocol.pipeline._discovered_tool_caller`` keep working.
    from cop_worker.protocol import pipeline as _pipeline

    return _pipeline._discovered_tool_caller(probe)


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
    caller = tool_caller or _tool_caller(probe)
    return profile, ReferenceV3Session(caller)


async def _verify_conformance(
    adapter: DeterministicProtocolAdapter,
    plan: ProtocolMappingPlan,
    probe,
    tool_caller: Callable[[str, dict], Awaitable[dict]] | None,
):
    from cop_worker.protocol import pipeline as _pipeline

    probes = _pipeline.ConformanceProbes(adapter, plan)
    local = probes.run_all()
    if not local.all_passed:
        raise ProtocolCompatibilityError(f"Conformance probes failed: {local.failed_probes()}")
    if probe.transport != TransportType.STDIO or tool_caller is not None or probe.stdio_command:
        caller = tool_caller or _tool_caller(probe)
        remote = await probes.run_remote(caller)
        if not remote.all_passed:
            raise ProtocolCompatibilityError(
                f"Remote conformance probes failed: {remote.failed_probes()}"
            )
        local.probes.extend(remote.probes)
    return local
