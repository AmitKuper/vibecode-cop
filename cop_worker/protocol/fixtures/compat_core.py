"""Compatible fixture: split commit and reveal tools."""

from __future__ import annotations

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.helpers import _intro, _tool
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)


def fixture_split_commit_reveal() -> Fixture:
    commit_tool = _tool(
        "commit_move",
        "Commit to a move",
        {
            "game_id": "string",
            "step": "integer",
            "role": "string",
            "commitment": "string",
            "hint": "string",
            "config_sha256": "string",
        },
        required=["game_id", "step", "role", "commitment"],
    )
    reveal_tool = _tool(
        "reveal_move",
        "Reveal committed move",
        {
            "game_id": "string",
            "step": "integer",
            "role": "string",
            "move": "string",
            "config_sha256": "string",
        },
        required=["game_id", "step", "role", "move"],
    )
    start_tool = _tool(
        "action",
        "Start/audit/result",
        {
            "game_id": "string",
            "phase": "string",
            "role": "string",
            "nonces": "object",
            "config_sha256": "string",
        },
    )
    intro = _intro("split-server", [commit_tool, reveal_tool, start_tool])
    plan = ProtocolMappingPlan(
        remote_tool_name="commit_move",
        remote_server_name="split-server",
        remote_schema_digest=intro.schema_digest,
        phase_mappings=[
            PhaseMapping(
                "start_game",
                "action",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("role", "role"),
                    FieldMapping("phase", "phase"),
                    FieldMapping("config_sha256", "config_sha256"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "commit",
                "commit_move",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("step", "step"),
                    FieldMapping("role", "role"),
                    FieldMapping("commitment", "commitment"),
                    FieldMapping("hint", "hint", required=False),
                    FieldMapping("config_sha256", "config_sha256"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "reveal",
                "reveal_move",
                [
                    FieldMapping("game_id", "game_id"),
                    FieldMapping("step", "step"),
                    FieldMapping("role", "role"),
                    FieldMapping("move", "move"),
                    FieldMapping("config_sha256", "config_sha256"),
                ],
                {"ok": "ok", "winner": "winner"},
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
                    FieldMapping("result_hash", "result_hash", required=False),
                ],
                {"ok": "ok"},
            ),
        ],
        verdict=CompatibilityVerdict.COMPATIBLE,
        confidence=0.95,
    )
    return Fixture(
        name="split_commit_reveal",
        description="Separate commit and reveal tools",
        compatible=True,
        introspection=intro,
        expected_plan=plan,
    )
