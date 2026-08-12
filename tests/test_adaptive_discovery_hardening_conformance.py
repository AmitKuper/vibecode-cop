"""Security and end-to-end discovery contracts for adaptive MCP: conformance."""

from __future__ import annotations

import pytest

from cop_worker.protocol.adapter import DeterministicProtocolAdapter
from cop_worker.protocol.conformance import ConformanceProbes
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan
from cop_worker.protocol.profile import ProtocolProfile


@pytest.mark.asyncio
async def test_remote_conformance_requires_stable_rejection() -> None:
    plan = ProtocolMappingPlan.native_plan()
    probes = ConformanceProbes(DeterministicProtocolAdapter(plan), plan)
    observed = []

    async def conform(tool_name, params):
        observed.append((tool_name, params))
        if tool_name == plan.conformance_tool:
            return {
                "ok": True,
                "game_id": params["game_id"],
                "phase": params["phase"],
                "idempotent": True,
                "side_effects": 0,
                "canonical_order": True,
                "canonical_json_bytes": True,
                "commitment_binding": True,
                "nonce_final_audit_only": True,
                "comprehensive_audit": True,
                "result_agreement": True,
            }
        return {
            "ok": False,
            "error": "invalid probe signature",
            "game_id": params["game_id"],
            "phase": params["phase"],
        }

    passed = await probes.run_remote(conform)
    assert passed.all_passed
    assert len(observed) == 4 * len(ProtocolMappingPlan.REQUIRED_PHASES)
    assert "private_key" not in str(observed)

    async def reject_only(_tool_name, params):
        return {
            "ok": False,
            "error": "invalid probe signature",
            "game_id": params.get("game_id"),
            "phase": params.get("phase"),
        }

    reject_only_report = await probes.run_remote(reject_only)
    assert not reject_only_report.all_passed
    assert len(reject_only_report.failed_probes()) == len(ProtocolMappingPlan.REQUIRED_PHASES)

    async def unsafe_accept(_tool_name, _params):
        return {"ok": True}

    failed = await probes.run_remote(unsafe_accept)
    assert not failed.all_passed
    assert len(failed.failed_probes()) == len(ProtocolMappingPlan.REQUIRED_PHASES)


def test_profile_hash_covers_every_mapping_detail() -> None:
    profile = ProtocolProfile.native()
    assert profile.verify_integrity()
    data = profile.to_dict()
    data["mapping_plan"]["phase_mappings"][0]["field_mappings"][0]["remote_field"] = "tampered"
    restored = ProtocolProfile.from_dict(data)
    assert not restored.verify_integrity()
