"""Compatible fixtures: nested envelope and packed-JSON request shapes."""

from __future__ import annotations

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.helpers import _intro, _tool
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)


def fixture_nested_envelope() -> Fixture:
    tools = [
        _tool(
            "action",
            "Send action in envelope",
            {
                "header": "object",
                "body": "object",
            },
        )
    ]
    intro = _intro("nested-server", tools)
    plan = ProtocolMappingPlan(
        remote_tool_name="action",
        remote_server_name="nested-server",
        remote_schema_digest=intro.schema_digest,
        phase_mappings=[
            PhaseMapping(
                "commit",
                "action",
                [
                    FieldMapping("game_id", "header.game_id"),
                    FieldMapping("step", "header.step"),
                    FieldMapping("role", "header.role"),
                    FieldMapping("commitment", "body.commitment"),
                    FieldMapping("config_sha256", "header.config_sha256"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "reveal",
                "action",
                [
                    FieldMapping("game_id", "header.game_id"),
                    FieldMapping("step", "header.step"),
                    FieldMapping("role", "header.role"),
                    FieldMapping("move", "body.move"),
                    FieldMapping("config_sha256", "header.config_sha256"),
                ],
                {"ok": "ok", "winner": "result.winner"},
            ),
            PhaseMapping(
                "start_game",
                "action",
                [
                    FieldMapping("game_id", "header.game_id"),
                    FieldMapping("role", "header.role"),
                    FieldMapping("phase", "header.phase"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "final_audit",
                "action",
                [
                    FieldMapping("game_id", "header.game_id"),
                    FieldMapping("nonces", "body.nonces"),
                    FieldMapping("role", "header.role"),
                    FieldMapping("phase", "header.phase"),
                ],
                {"ok": "ok"},
            ),
            PhaseMapping(
                "result_agreement",
                "action",
                [
                    FieldMapping("game_id", "header.game_id"),
                    FieldMapping("role", "header.role"),
                    FieldMapping("phase", "header.phase"),
                ],
                {"ok": "ok"},
            ),
        ],
        verdict=CompatibilityVerdict.COMPATIBLE,
        confidence=0.85,
    )
    return Fixture(
        name="nested_envelope",
        description="Actions wrapped in header/body envelope",
        compatible=True,
        introspection=intro,
        expected_plan=plan,
    )


def fixture_packed_json() -> Fixture:
    tools = [
        _tool(
            "action",
            "Packed JSON action",
            {
                "game_id": "string",
                "packed_message": "string",
                "signature": "string",
            },
        )
    ]
    return Fixture(
        name="packed_json",
        description="Canonical message packed as JSON string + signature",
        compatible=True,
        introspection=_intro("packed-server", tools),
        expected_plan=ProtocolMappingPlan.packed_envelope_plan(
            schema_digest=_intro("packed-server", tools).schema_digest,
            server_name="packed-server",
        ),
    )
