"""Construct a ProtocolMappingPlan from a parsed LLM response (mixin)."""

from __future__ import annotations

import logging

from cop_worker.protocol.introspector import IntrospectionResult
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)

logger = logging.getLogger(__name__)


class ProtocolAgentPlanBuildMixin:
    """LLM response -> validated ProtocolMappingPlan."""

    def _build_plan_from_llm(self, parsed: dict, intro: IntrospectionResult) -> ProtocolMappingPlan:
        if parsed.get("phase_mappings"):
            payload = dict(parsed)
            payload["remote_server_name"] = intro.server_name
            payload["remote_schema_digest"] = intro.schema_digest
            payload["agent_model"] = self._model_id
            payload["agent_version"] = "2.0"
            plan = ProtocolMappingPlan.from_dict(payload)
            self._validate_remote_plan(plan, intro)
            return plan
        verdict = CompatibilityVerdict(parsed.get("verdict", "COMPATIBLE"))
        renames: dict[str, str] = parsed.get("field_renames", {})
        tool_name: str = parsed.get("remote_tool_name", "action")
        tool = intro.get_tool(tool_name) or (intro.tools[0] if intro.tools else None)
        if not tool:
            return ProtocolMappingPlan.native_plan(server_name=intro.server_name)
        tool_name = tool.name

        props = tool.input_schema.get("properties", {})
        phase_mappings = []
        for phase in ProtocolMappingPlan.REQUIRED_PHASES:
            fms = []
            for cf in self._canonical_fields_for_phase(phase):
                remote = renames.get(cf, cf if cf in props else self._closest_match(cf, props))
                if remote:
                    fms.append(
                        FieldMapping(
                            canonical_field=cf,
                            remote_field=remote,
                            required=cf not in {"timestamp", "hint", "result_hash"},
                        )
                    )
            phase_mappings.append(
                PhaseMapping(
                    phase=phase,
                    remote_tool=tool_name,
                    field_mappings=fms,
                    response_extraction={"ok": "ok", "game_id": "game_id", "phase": "phase"},
                    multiphase_envelope=any(
                        item.canonical_field in {"phase", "message_json"} for item in fms
                    ),
                )
            )

        return ProtocolMappingPlan(
            remote_tool_name=tool_name,
            remote_server_name=intro.server_name,
            remote_schema_digest=intro.schema_digest,
            phase_mappings=phase_mappings,
            capability_gaps=parsed.get("capability_gaps", []),
            unresolved_questions=parsed.get("unresolved_questions", []),
            verdict=verdict,
            confidence=float(parsed.get("confidence", 0.9)),
            agent_model=self._model_id,
            agent_version="1.0",
        )
