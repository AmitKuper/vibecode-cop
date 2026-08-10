"""Compatible fixtures: nested response fields and optional extras."""

from __future__ import annotations

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.helpers import _intro, _tool
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)


def fixture_nested_response() -> Fixture:
    tools = [
        _tool(
            "action",
            "Returns nested response",
            {
                "game_id": "string",
                "step": "integer",
                "role": "string",
                "phase": "string",
                "commitment": "string",
                "move": "string",
                "nonces": "object",
                "config_sha256": "string",
            },
        )
    ]
    _nested_resp = {"ok": "data.ok", "winner": "data.winner", "phase": "data.phase"}
    _base = [
        FieldMapping("game_id", "game_id"),
        FieldMapping("step", "step"),
        FieldMapping("role", "role"),
        FieldMapping("phase", "phase"),
        FieldMapping("config_sha256", "config_sha256"),
    ]
    return Fixture(
        name="nested_response",
        description="Response fields nested under 'data' key",
        compatible=True,
        introspection=_intro("nested-resp-server", tools),
        expected_plan=ProtocolMappingPlan(
            remote_tool_name="action",
            remote_server_name="nested-resp-server",
            remote_schema_digest=_intro("nested-resp-server", tools).schema_digest,
            phase_mappings=[
                PhaseMapping("start_game", "action", _base, _nested_resp),
                PhaseMapping(
                    "commit",
                    "action",
                    _base
                    + [
                        FieldMapping("commitment", "commitment"),
                    ],
                    _nested_resp,
                ),
                PhaseMapping(
                    "reveal",
                    "action",
                    _base
                    + [
                        FieldMapping("move", "move"),
                    ],
                    _nested_resp,
                ),
                PhaseMapping(
                    "final_audit",
                    "action",
                    _base
                    + [
                        FieldMapping("nonces", "nonces"),
                    ],
                    _nested_resp,
                ),
                PhaseMapping("result_agreement", "action", _base, _nested_resp),
            ],
            verdict=CompatibilityVerdict.COMPATIBLE,
            confidence=0.9,
        ),
    )


def fixture_optional_extra_fields() -> Fixture:
    tools = [
        _tool(
            "action",
            "Accepts extra optional fields",
            {
                "game_id": "string",
                "step": "integer",
                "role": "string",
                "phase": "string",
                "commitment": "string",
                "move": "string",
                "nonces": "object",
                "config_sha256": "string",
                "client_version": "string",  # extra optional
                "trace_id": "string",  # extra optional
            },
        )
    ]
    intro = _intro("extra-fields-server", tools)
    plan = ProtocolMappingPlan.native_plan(server_name="extra-fields-server")
    plan = ProtocolMappingPlan(
        remote_tool_name="action",
        remote_server_name="extra-fields-server",
        remote_schema_digest=intro.schema_digest,
        phase_mappings=plan.phase_mappings,
        verdict=CompatibilityVerdict.COMPATIBLE,
        confidence=1.0,
    )
    return Fixture(
        name="optional_extra_fields",
        description="Remote accepts additional optional fields (ignored)",
        compatible=True,
        introspection=intro,
        expected_plan=plan,
    )
