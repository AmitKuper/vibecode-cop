"""ProtocolMappingPlan: declarative plan produced once by the ProtocolUnderstandingAgent.

The plan is produced before gameplay. During gameplay, the DeterministicProtocolAdapter
applies the plan using DSL transforms only — no LLM is called per turn.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class CompatibilityVerdict(enum.StrEnum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class FieldMapping:
    """Maps one canonical field to a remote field path, with optional transform."""

    canonical_field: str
    remote_field: str
    transform: str = "identity"
    transform_args: dict = field(default_factory=dict)
    required: bool = True
    constant_value: Any = None


@dataclass
class PhaseMapping:
    """Maps one canonical protocol phase to a remote tool call."""

    phase: str
    remote_tool: str
    field_mappings: list[FieldMapping] = field(default_factory=list)
    response_extraction: dict[str, str] = field(default_factory=dict)
    notes: str = ""


@dataclass
class ProtocolMappingPlan:
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

    # Canonical phases that must be mappable for gameplay
    REQUIRED_PHASES = frozenset(
        ["start_game", "commit", "reveal", "final_audit", "result_agreement"]
    )

    def is_compatible(self) -> bool:
        return self.verdict == CompatibilityVerdict.COMPATIBLE

    def has_required_phases(self) -> bool:
        mapped = {pm.phase for pm in self.phase_mappings}
        return self.REQUIRED_PHASES.issubset(mapped)

    def plan_hash(self) -> str:
        payload = {
            "remote_tool": self.remote_tool_name,
            "schema_digest": self.remote_schema_digest,
            "phases": [pm.phase for pm in self.phase_mappings],
            "verdict": self.verdict.value,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def to_dict(self) -> dict:
        return {
            "remote_tool_name": self.remote_tool_name,
            "remote_server_name": self.remote_server_name,
            "remote_schema_digest": self.remote_schema_digest,
            "phase_mappings": [
                {
                    "phase": pm.phase,
                    "remote_tool": pm.remote_tool,
                    "field_mappings": [
                        {
                            "canonical_field": fm.canonical_field,
                            "remote_field": fm.remote_field,
                            "transform": fm.transform,
                            "transform_args": fm.transform_args,
                            "required": fm.required,
                            "constant_value": fm.constant_value,
                        }
                        for fm in pm.field_mappings
                    ],
                    "response_extraction": pm.response_extraction,
                    "notes": pm.notes,
                }
                for pm in self.phase_mappings
            ],
            "enum_mappings": self.enum_mappings,
            "capability_gaps": self.capability_gaps,
            "unresolved_questions": self.unresolved_questions,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "agent_model": self.agent_model,
            "agent_version": self.agent_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProtocolMappingPlan:
        phase_mappings = []
        for pm_d in d.get("phase_mappings", []):
            field_mappings = [
                FieldMapping(
                    canonical_field=fm["canonical_field"],
                    remote_field=fm["remote_field"],
                    transform=fm.get("transform", "identity"),
                    transform_args=fm.get("transform_args", {}),
                    required=fm.get("required", True),
                    constant_value=fm.get("constant_value"),
                )
                for fm in pm_d.get("field_mappings", [])
            ]
            phase_mappings.append(
                PhaseMapping(
                    phase=pm_d["phase"],
                    remote_tool=pm_d["remote_tool"],
                    field_mappings=field_mappings,
                    response_extraction=pm_d.get("response_extraction", {}),
                    notes=pm_d.get("notes", ""),
                )
            )
        return cls(
            remote_tool_name=d.get("remote_tool_name", "action"),
            remote_server_name=d.get("remote_server_name", "unknown"),
            remote_schema_digest=d.get("remote_schema_digest", ""),
            phase_mappings=phase_mappings,
            enum_mappings=d.get("enum_mappings", {}),
            capability_gaps=d.get("capability_gaps", []),
            unresolved_questions=d.get("unresolved_questions", []),
            verdict=CompatibilityVerdict(d.get("verdict", "COMPATIBLE")),
            confidence=d.get("confidence", 1.0),
            agent_model=d.get("agent_model", "deterministic"),
            agent_version=d.get("agent_version", "1.0"),
        )

    @classmethod
    def native_plan(
        cls, tool_name: str = "action", server_name: str = "native"
    ) -> ProtocolMappingPlan:
        """Identity mapping for a native server using canonical `action` tool."""
        _base = [
            FieldMapping("game_id", "game_id"),
            FieldMapping("step", "step"),
            FieldMapping("role", "role"),
            FieldMapping("phase", "phase"),
            FieldMapping("config_sha256", "config_sha256"),
            FieldMapping("timestamp", "timestamp", required=False),
        ]
        _phase_extra: dict[str, list[FieldMapping]] = {
            "start_game": [FieldMapping("gamelet", "gamelet", required=False)],
            "commit": [
                FieldMapping("commitment", "commitment"),
                FieldMapping("hint", "hint", required=False),
            ],
            "reveal": [FieldMapping("move", "move")],
            "final_audit": [FieldMapping("nonces", "nonces")],
            "result_agreement": [
                FieldMapping("result_hash", "result_hash", required=False),
                FieldMapping("signed_agreement", "signed_agreement", required=False),
            ],
        }
        return cls(
            remote_tool_name=tool_name,
            remote_server_name=server_name,
            remote_schema_digest="native",
            phase_mappings=[
                PhaseMapping(
                    phase=phase,
                    remote_tool=tool_name,
                    field_mappings=_base + _phase_extra.get(phase, []),
                    response_extraction={"ok": "ok", "phase": "phase"},
                )
                for phase in cls.REQUIRED_PHASES
            ],
            verdict=CompatibilityVerdict.COMPATIBLE,
            confidence=1.0,
            agent_model="native-identity",
        )
