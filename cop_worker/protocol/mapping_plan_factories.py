"""Built-in plan factories: native, signed-envelope, packed-envelope (mixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cop_worker.protocol.mapping_plan_types import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cop_worker.protocol.mapping_plan import ProtocolMappingPlan


from cop_worker.protocol.mapping_plan_packed import MappingPlanPackedFactoryMixin


class MappingPlanFactoriesMixin(MappingPlanPackedFactoryMixin):
    """Constructors for the three built-in dialect plans."""

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
            FieldMapping("signature", "signature"),
            FieldMapping("timestamp", "timestamp", required=False),
        ]
        _phase_extra: dict[str, list[FieldMapping]] = {
            "start_game": [FieldMapping("gamelet", "gamelet")],
            "commit": [
                FieldMapping("commitment", "commitment"),
                FieldMapping("hint", "hint", required=False),
            ],
            "reveal": [FieldMapping("move", "move")],
            "final_audit": [FieldMapping("nonces", "nonces")],
            "audit_summary": [FieldMapping("signed_audit_summary", "signed_audit_summary")],
            "game_end": [FieldMapping("reason", "reason")],
            "result_agreement": [
                FieldMapping("result_hash", "result_hash", required=False),
                FieldMapping("signed_agreement", "signed_agreement"),
            ],
            "abort": [FieldMapping("reason", "reason")],
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
                    response_extraction={"ok": "ok", "game_id": "game_id", "phase": "phase"},
                    multiphase_envelope=True,
                )
                for phase in sorted(cls.REQUIRED_PHASES)
            ],
            verdict=CompatibilityVerdict.COMPATIBLE,
            confidence=1.0,
            agent_model="native-identity",
        )

    @classmethod
    def signed_envelope_plan(
        cls,
        *,
        schema_digest: str,
        server_name: str,
        action_tool: str = "action",
        start_tool: str = "start_game",
    ) -> ProtocolMappingPlan:
        """Plan for the course protocol's signed ``message_json`` envelope."""
        action_fields = [
            FieldMapping("game_id", "game_id"),
            FieldMapping("message_json", "message_json"),
            FieldMapping("signature", "signature"),
        ]
        return cls(
            remote_tool_name=action_tool,
            remote_server_name=server_name,
            remote_schema_digest=schema_digest,
            phase_mappings=[
                PhaseMapping(
                    phase="start_game",
                    remote_tool=start_tool,
                    field_mappings=[
                        FieldMapping("message_json", "message_json"),
                        FieldMapping("signature", "signature"),
                    ],
                    response_extraction={"ok": "ok", "game_id": "game_id", "phase": "phase"},
                    multiphase_envelope=True,
                ),
                *[
                    PhaseMapping(
                        phase=phase,
                        remote_tool=action_tool,
                        field_mappings=list(action_fields),
                        response_extraction={
                            "ok": "ok",
                            "phase": "phase",
                            "game_id": "game_id",
                            "winner": "winner",
                        },
                        multiphase_envelope=True,
                    )
                    for phase in (
                        "commit",
                        "reveal",
                        "final_audit",
                        "game_end",
                        "result_agreement",
                        "audit_summary",
                        "abort",
                    )
                ],
            ],
            verdict=CompatibilityVerdict.COMPATIBLE,
            confidence=1.0,
            agent_model="deterministic-signed-envelope",
        )
