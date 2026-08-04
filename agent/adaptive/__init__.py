"""Adaptive MCP Protocol Pipeline.

Pre-game: TransportProbe → MCPIntrospector → ProtocolUnderstandingAgent
          → ProtocolMappingPlan → StaticSemanticVerifier → ConformanceProbes
          → ProtocolProfile (signed + hashed, included in Step-0)

During gameplay: DeterministicProtocolAdapter (no LLM, DSL only).
"""

from agent.adaptive.adapter import DeterministicProtocolAdapter
from agent.adaptive.dsl import AdapterDSL, DSLTransform
from agent.adaptive.introspector import MCPIntrospector
from agent.adaptive.mapping_plan import CompatibilityVerdict, ProtocolMappingPlan
from agent.adaptive.pipeline import run_adaptive_negotiation
from agent.adaptive.profile import ProtocolProfile
from agent.adaptive.transport_probe import TransportProbe, TransportType

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
]
