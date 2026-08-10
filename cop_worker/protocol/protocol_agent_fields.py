"""Canonical field mapping helpers for the protocol planner (mixin)."""

from __future__ import annotations

import logging

from cop_worker.protocol.introspector import IntrospectionResult
from cop_worker.protocol.mapping_plan import (
    FieldMapping,
    ProtocolMappingPlan,
)

logger = logging.getLogger(__name__)


class ProtocolAgentFieldsMixin:
    """Field-name mapping between canonical and discovered schemas."""

    def _map_canonical_fields(self, phase: str, props: dict) -> list[FieldMapping]:
        """Map canonical fields to remote props by name matching."""
        canonical = [
            "game_id",
            "step",
            "role",
            "phase",
            "config_sha256",
            "timestamp",
            "signature",
        ]
        if phase == "start_game":
            canonical += ["gamelet"]
        elif phase == "commit":
            canonical += ["commitment", "hint"]
        elif phase == "reveal":
            canonical += ["move"]
        elif phase == "final_audit":
            canonical += ["nonces"]
        elif phase == "audit_summary":
            canonical += ["signed_audit_summary"]
        elif phase == "game_end":
            canonical += ["reason"]
        elif phase == "result_agreement":
            canonical += ["result_hash", "signed_agreement"]
        elif phase == "abort":
            canonical += ["reason"]

        fms = []
        for cf in canonical:
            remote = cf if cf in props else self._closest_match(cf, props)
            if remote:
                fms.append(
                    FieldMapping(
                        canonical_field=cf,
                        remote_field=remote,
                        required=cf not in {"timestamp", "hint", "result_hash"},
                    )
                )
        return fms

    @staticmethod
    def _validate_remote_plan(plan: ProtocolMappingPlan, intro: IntrospectionResult) -> None:
        tools = {tool.name: tool for tool in intro.tools}
        if plan.conformance_tool not in tools:
            raise ValueError(f"LLM selected unknown conformance tool {plan.conformance_tool!r}")
        for phase in plan.phase_mappings:
            if phase.remote_tool not in tools:
                raise ValueError(f"LLM selected unknown remote tool {phase.remote_tool!r}")
            roots = tools[phase.remote_tool].input_schema.get("properties", {})
            for mapping in phase.field_mappings:
                root = mapping.remote_field.split(".", 1)[0]
                if root not in roots:
                    raise ValueError(
                        f"LLM selected unknown field {mapping.remote_field!r} "
                        f"for tool {phase.remote_tool!r}"
                    )

    def _canonical_fields_for_phase(self, phase: str) -> list[str]:
        base = [
            "game_id",
            "step",
            "role",
            "phase",
            "config_sha256",
            "timestamp",
            "signature",
        ]
        extras = {
            "start_game": ["gamelet"],
            "commit": ["commitment", "hint"],
            "reveal": ["move"],
            "final_audit": ["nonces"],
            "audit_summary": ["signed_audit_summary"],
            "game_end": ["reason"],
            "result_agreement": ["result_hash", "signed_agreement"],
            "abort": ["reason"],
        }
        return base + extras.get(phase, [])

    @staticmethod
    def _closest_match(field: str, props: dict) -> str | None:
        # Protected semantics must never be inferred from substring overlap
        # (for example ``move`` is a substring of ``move_commitment``). Any
        # non-exact rename must be explicit in a typed, schema-checked plan.
        return field if field in props else None
