"""Packed-envelope plan factory (mixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cop_worker.protocol.mapping_plan_types import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cop_worker.protocol.mapping_plan import ProtocolMappingPlan


class MappingPlanPackedFactoryMixin:
    """Constructor for the packed-JSON envelope dialect plan."""

    @classmethod
    def packed_envelope_plan(
        cls,
        *,
        schema_digest: str,
        server_name: str,
        tool_name: str = "action",
    ) -> ProtocolMappingPlan:
        """Plan carrying the complete signed canonical JSON in a renamed field."""
        fields = [
            FieldMapping("game_id", "game_id"),
            FieldMapping("message_json", "packed_message"),
            FieldMapping("signature", "signature"),
        ]
        return cls(
            remote_tool_name=tool_name,
            remote_server_name=server_name,
            remote_schema_digest=schema_digest,
            phase_mappings=[
                PhaseMapping(
                    phase=phase,
                    remote_tool=tool_name,
                    field_mappings=list(fields),
                    response_extraction={"ok": "ok", "game_id": "game_id", "phase": "phase"},
                    multiphase_envelope=True,
                )
                for phase in sorted(cls.REQUIRED_PHASES)
            ],
            verdict=CompatibilityVerdict.COMPATIBLE,
            confidence=1.0,
            agent_model="deterministic-packed-envelope",
        )
