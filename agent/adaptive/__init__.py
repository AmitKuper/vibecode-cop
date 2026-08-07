"""Adaptive MCP Protocol Pipeline — compatibility shim.

All implementation has moved to ``cop_worker.protocol``.  This module
re-exports the public surface so that legacy ``agent.adaptive.*`` imports
continue to work after the Phase-1 restructure.
"""

# Re-export everything from the new canonical location.
from cop_worker.protocol.adapter import DeterministicProtocolAdapter  # noqa: F401
from cop_worker.protocol.dsl import AdapterDSL, DSLTransform  # noqa: F401
from cop_worker.protocol.introspector import MCPIntrospector  # noqa: F401
from cop_worker.protocol.mapping_plan import CompatibilityVerdict, ProtocolMappingPlan  # noqa: F401
from cop_worker.protocol.pipeline import run_adaptive_negotiation  # noqa: F401
from cop_worker.protocol.profile import ProtocolProfile  # noqa: F401
from cop_worker.protocol.reference_v3 import (  # noqa: F401
    ReferenceV3Session,
    build_negotiation,
    build_turn,
    default_terms,
    register_reference_v3_tools,
)
from cop_worker.protocol.transport_probe import TransportProbe, TransportType  # noqa: F401

__all__ = [
    "TransportProbe",
    "TransportType",
    "MCPIntrospector",
    "ProtocolMappingPlan",
    "CompatibilityVerdict",
    "AdapterDSL",
    "DSLTransform",
    "DeterministicProtocolAdapter",
    "ProtocolProfile",
    "run_adaptive_negotiation",
    "ReferenceV3Session",
    "build_negotiation",
    "build_turn",
    "default_terms",
    "register_reference_v3_tools",
]
