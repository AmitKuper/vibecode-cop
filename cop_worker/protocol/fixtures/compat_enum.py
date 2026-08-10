"""Compatible fixture: enum synonyms (N->NORTH etc.)."""

from __future__ import annotations

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.helpers import _intro, _tool
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)


def fixture_enum_synonyms() -> Fixture:
    tools = [
        _tool(
            "action",
            "Game action with long move names",
            {
                "game_id": "string",
                "step": "integer",
                "role": "string",
                "phase": "string",
                "commitment": "string",
                "move": "string",  # expects NORTH/SOUTH/EAST/WEST/STAY
                "nonces": "object",
                "config_sha256": "string",
            },
        )
    ]
    intro = _intro("enum-server", tools)
    enum_map = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}
    plan = ProtocolMappingPlan(
        remote_tool_name="action",
        remote_server_name="enum-server",
        remote_schema_digest=intro.schema_digest,
        phase_mappings=[
            PhaseMapping(
                "commit",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("step", "step"),
                    FieldMapping("role", "role"),
                    FieldMapping("commitment", "commitment"),
                    FieldMapping("config_sha256", "config_sha256"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "reveal",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("step", "step"),
                    FieldMapping("role", "role"),
                    FieldMapping(
                        "move", "move", transform="enum_map", transform_args={"mapping": enum_map}
                    ),
                    FieldMapping("config_sha256", "config_sha256"),
                ],
                {"ok": "ok", "winner": "winner"},
            ),
            PhaseMapping(
                "start_game",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("role", "role"),
                    FieldMapping("phase", "phase"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "final_audit",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("nonces", "nonces"),
                    FieldMapping("role", "role"),
                    FieldMapping("phase", "phase"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "result_agreement",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("role", "role"),
                    FieldMapping("phase", "phase"),
                ],
                {"ok": "ok"},
            ),
        ],
        enum_mappings=enum_map,
        verdict=CompatibilityVerdict.COMPATIBLE,
        confidence=0.92,
    )
    return Fixture(
        name="enum_synonyms",
        description="Move enum: N→NORTH, S→SOUTH, etc.",
        compatible=True,
        introspection=intro,
        expected_plan=plan,
    )
