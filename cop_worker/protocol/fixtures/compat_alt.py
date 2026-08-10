"""Compatible fixture: alternate tool names."""

from __future__ import annotations

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.helpers import _intro, _tool
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)


def fixture_alt_tool_name() -> Fixture:
    tools = [
        _tool(
            "game_move",
            "Perform a game move",
            {
                "game_id": "string",
                "step_num": "integer",
                "player_role": "string",
                "action_phase": "string",
                "move_commitment": "string",
                "action": "string",
                "audit_nonces": "object",
                "config_hash": "string",
                "ts": "string",
            },
        )
    ]
    intro = _intro("alt-name-server", tools)
    plan = ProtocolMappingPlan(
        remote_tool_name="game_move",
        remote_server_name="alt-name-server",
        remote_schema_digest=intro.schema_digest,
        phase_mappings=[
            PhaseMapping(
                "commit",
                "game_move",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("step", "step_num"),
                    FieldMapping("role", "player_role"),
                    FieldMapping("phase", "action_phase"),
                    FieldMapping("commitment", "move_commitment"),
                    FieldMapping("config_sha256", "config_hash"),
                    FieldMapping("timestamp", "ts", required=False),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "reveal",
                "game_move",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("step", "step_num"),
                    FieldMapping("role", "player_role"),
                    FieldMapping("move", "action"),
                    FieldMapping("config_sha256", "config_hash"),
                ],
                {"ok": "ok", "winner": "winner"},
            ),
            PhaseMapping(
                "start_game",
                "game_move",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("role", "player_role"),
                    FieldMapping("phase", "action_phase"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "final_audit",
                "game_move",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("nonces", "audit_nonces"),
                    FieldMapping("phase", "action_phase"),
                    FieldMapping("role", "player_role"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "result_agreement",
                "game_move",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("phase", "action_phase"),
                    FieldMapping("role", "player_role"),
                ],
                {"ok": "ok"},
            ),
        ],
        verdict=CompatibilityVerdict.COMPATIBLE,
        confidence=0.9,
    )
    return Fixture(
        name="alt_tool_name",
        description="Alternate tool name: game_move with field renames",
        compatible=True,
        introspection=intro,
        expected_plan=plan,
    )
