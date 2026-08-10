"""Serialization of ProtocolMappingPlan (mixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cop_worker.protocol.mapping_plan_types import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cop_worker.protocol.mapping_plan import ProtocolMappingPlan


class MappingPlanSerdeMixin:
    """to_dict/from_dict round-trip."""

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
                    "required_response_fields": pm.required_response_fields,
                    "expected_errors": pm.expected_errors,
                    "idempotent": pm.idempotent,
                    "multiphase_envelope": pm.multiphase_envelope,
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
            "conformance_tool": self.conformance_tool,
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
                    required_response_fields=pm_d.get(
                        "required_response_fields", ["ok", "game_id", "phase"]
                    ),
                    expected_errors=pm_d.get(
                        "expected_errors",
                        ["invalid_signature", "out_of_order", "duplicate_conflict"],
                    ),
                    idempotent=pm_d.get("idempotent", True),
                    multiphase_envelope=pm_d.get("multiphase_envelope", False),
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
            conformance_tool=d.get("conformance_tool", "protocol_conformance"),
        )
