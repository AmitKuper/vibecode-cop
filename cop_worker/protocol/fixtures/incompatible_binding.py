"""Incompatible fixtures: commitment-binding violations (reject before first commit)."""

from __future__ import annotations

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.helpers import _intro, _tool
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    PhaseMapping,
    ProtocolMappingPlan,
)


def fixture_incompat_nonce_in_reveal() -> Fixture:
    tools = [
        _tool(
            "action",
            "Requires nonce during ordinary reveal",
            {
                "game_id": "string",
                "step": "integer",
                "role": "string",
                "phase": "string",
                "commitment": "string",
                "move": "string",
                "nonce": "string",  # VIOLATION: nonce required in reveal
                "config_sha256": "string",
            },
            required=["game_id", "step", "role", "phase", "commitment", "move", "nonce"],
        )
    ]
    return Fixture(
        name="incompat_nonce_in_reveal",
        description="INCOMPATIBLE: requires nonce during ordinary reveal phase",
        compatible=False,
        introspection=_intro("nonce-reveal-server", tools),
        reject_reason="nonce required during reveal violates commit-reveal secrecy",
    )


def fixture_incompat_no_commitment() -> Fixture:
    tools = [
        _tool(
            "action",
            "No commitment field",
            {
                "game_id": "string",
                "step": "integer",
                "role": "string",
                "move": "string",  # sends move directly without commit-reveal
                "config_sha256": "string",
            },
        )
    ]
    return Fixture(
        name="incompat_no_commitment",
        description="INCOMPATIBLE: no way to bind a commitment (no commit-reveal)",
        compatible=False,
        introspection=_intro("no-commit-server", tools),
        reject_reason="commitment field absent — cannot enforce commit-reveal integrity",
    )


def fixture_incompat_no_final_audit() -> Fixture:
    tools = [
        _tool(
            "action",
            "Missing final_audit support",
            {
                "game_id": "string",
                "step": "integer",
                "role": "string",
                "phase": "string",  # only supports commit/reveal/result
                "commitment": "string",
                "move": "string",
            },
        )
    ]
    intro = _intro("no-audit-server", tools)
    plan = ProtocolMappingPlan(
        remote_tool_name="action",
        remote_server_name="no-audit-server",
        remote_schema_digest=intro.schema_digest,
        phase_mappings=[
            # Deliberately omit final_audit
            PhaseMapping("commit", "action", [], {}),
            PhaseMapping("reveal", "action", [], {}),
            PhaseMapping("result_agreement", "action", [], {}),
            PhaseMapping("start_game", "action", [], {}),
            # final_audit missing
        ],
        verdict=CompatibilityVerdict.INCOMPATIBLE,
        capability_gaps=["no final_audit phase"],
    )
    return Fixture(
        name="incompat_no_final_audit",
        description="INCOMPATIBLE: missing final_audit phase",
        compatible=False,
        introspection=intro,
        expected_plan=plan,
        reject_reason="final_audit phase required for bilateral audit integrity",
    )
