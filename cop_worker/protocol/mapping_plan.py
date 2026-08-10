"""ProtocolMappingPlan: declarative plan produced once by the ProtocolUnderstandingAgent.

The plan is produced before gameplay. During gameplay, the DeterministicProtocolAdapter
applies the plan using DSL transforms only â€” no LLM is called per turn.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from cop_worker.protocol.mapping_plan_factories import MappingPlanFactoriesMixin
from cop_worker.protocol.mapping_plan_serde import MappingPlanSerdeMixin
from cop_worker.protocol.mapping_plan_types import (  # noqa: F401  (public re-exports)
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
)


@dataclass
class ProtocolMappingPlan(MappingPlanSerdeMixin, MappingPlanFactoriesMixin):
    """Declarative mapping from canonical protocol to remote protocol.

    Produced ONCE by the ProtocolUnderstandingAgent (LLM call) before gameplay.
    Immutable during gameplay.
    """

    remote_tool_name: str
    remote_server_name: str
    remote_schema_digest: str
    phase_mappings: list[PhaseMapping] = field(default_factory=list)
    enum_mappings: dict[str, str] = field(default_factory=dict)
    capability_gaps: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    verdict: CompatibilityVerdict = CompatibilityVerdict.COMPATIBLE
    confidence: float = 1.0
    agent_model: str = "deterministic"
    agent_version: str = "1.0"
    conformance_tool: str = "protocol_conformance"

    # Canonical phases that must be mappable for gameplay
    REQUIRED_PHASES = frozenset(
        [
            "start_game",
            "commit",
            "reveal",
            "final_audit",
            "audit_summary",
            "game_end",
            "result_agreement",
            "abort",
        ]
    )

    def is_compatible(self) -> bool:
        return self.verdict == CompatibilityVerdict.COMPATIBLE

    def has_required_phases(self) -> bool:
        mapped = {pm.phase for pm in self.phase_mappings}
        return self.REQUIRED_PHASES.issubset(mapped)

    def plan_hash(self) -> str:
        # Hash every executable mapping detail.  Hashing only phase names lets
        # an attacker change field paths/transforms while retaining the same
        # allegedly locked plan hash.
        payload = self.to_dict()
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
