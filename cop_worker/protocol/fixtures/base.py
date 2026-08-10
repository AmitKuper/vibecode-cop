"""Fixture dataclass for adaptive MCP acceptance testing (see package __init__)."""

from __future__ import annotations

from dataclasses import dataclass

from cop_worker.protocol.introspector import IntrospectionResult, ToolSchema
from cop_worker.protocol.mapping_plan import (
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)


@dataclass
class Fixture:
    name: str
    description: str
    compatible: bool
    introspection: IntrospectionResult
    expected_plan: ProtocolMappingPlan | None = None
    reject_reason: str = ""

    def __post_init__(self) -> None:
        """Keep compatible fixture plans aligned with the full lifecycle contract."""
        plan = self.expected_plan
        if not self.compatible or plan is None:
            return
        template = next(
            (mapping for mapping in plan.phase_mappings if mapping.phase == "result_agreement"),
            None,
        )
        if template is None:
            return
        if not any(tool.name == plan.conformance_tool for tool in self.introspection.tools):
            self.introspection.tools.append(
                ToolSchema(
                    plan.conformance_tool,
                    "Side-effect-free protocol conformance",
                    {
                        "type": "object",
                        "properties": {
                            "phase": {"type": "string"},
                            "game_id": {"type": "string"},
                            "request_digest": {"type": "string"},
                            "idempotency_key": {"type": "string"},
                        },
                    },
                )
            )
        mandatory = {
            "start_game": "gamelet",
            "commit": "commitment",
            "reveal": "move",
            "final_audit": "nonces",
            "audit_summary": "signed_audit_summary",
            "game_end": "reason",
            "result_agreement": "signed_agreement",
            "abort": "reason",
        }
        for mapping in plan.phase_mappings:
            fields = {item.canonical_field for item in mapping.field_mappings}
            if not {"message_json", "signature"}.issubset(fields) and "signature" not in fields:
                mapping.field_mappings.append(FieldMapping("signature", "signature"))
            if mandatory.get(mapping.phase) not in fields and not {
                "message_json",
                "signature",
            }.issubset(fields):
                semantic = mandatory[mapping.phase]
                mapping.field_mappings.append(FieldMapping(semantic, semantic))
            mapping.response_extraction.setdefault(
                "phase",
                (
                    "data.phase"
                    if mapping.response_extraction.get("ok", "").startswith("data.")
                    else "phase"
                ),
            )
            mapping.response_extraction.setdefault(
                "game_id",
                (
                    "data.game_id"
                    if mapping.response_extraction.get("phase", "").startswith("data.")
                    else "game_id"
                ),
            )
        packed = {item.canonical_field for item in template.field_mappings}.issuperset(
            {"message_json", "signature"}
        )
        additions = {
            "game_end": ("reason", True),
            "audit_summary": ("signed_audit_summary", True),
            "abort": ("reason", True),
        }
        for phase, (semantic_field, required) in additions.items():
            if any(mapping.phase == phase for mapping in plan.phase_mappings):
                continue
            if packed:
                fields = list(template.field_mappings)
            else:
                fields = [
                    item
                    for item in template.field_mappings
                    if item.canonical_field not in {"result_hash", "signed_agreement"}
                ]
                remote = semantic_field
                signed_mapping = next(
                    (
                        item
                        for item in template.field_mappings
                        if item.canonical_field == "signed_agreement"
                    ),
                    None,
                )
                if signed_mapping is not None and "." in signed_mapping.remote_field:
                    root = signed_mapping.remote_field.rsplit(".", 1)[0]
                    remote = f"{root}.{semantic_field}"
                fields.append(FieldMapping(semantic_field, remote, required=required))
            plan.phase_mappings.append(
                PhaseMapping(
                    phase,
                    template.remote_tool,
                    fields,
                    dict(template.response_extraction),
                    "fixture full lifecycle",
                    multiphase_envelope=packed
                    or any(item.canonical_field == "phase" for item in fields),
                )
            )
        tool_counts: dict[str, int] = {}
        for mapping in plan.phase_mappings:
            tool_counts[mapping.remote_tool] = tool_counts.get(mapping.remote_tool, 0) + 1
        for mapping in plan.phase_mappings:
            if tool_counts[mapping.remote_tool] <= 1:
                continue
            fields = {item.canonical_field for item in mapping.field_mappings}
            if not fields.issuperset({"message_json", "signature"}) and "phase" not in fields:
                game_id_mapping = next(
                    (item for item in mapping.field_mappings if item.canonical_field == "game_id"),
                    None,
                )
                remote_phase = "phase"
                if game_id_mapping is not None and "." in game_id_mapping.remote_field:
                    root = game_id_mapping.remote_field.rsplit(".", 1)[0]
                    remote_phase = f"{root}.phase"
                mapping.field_mappings.append(FieldMapping("phase", remote_phase))
            mapping.multiphase_envelope = True
