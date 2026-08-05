"""Counted bilateral ResultAgreement success and active-exchange contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.adaptive.profile import ProtocolProfile
from agent.audit.audit_summary import AuditSummary, create_signed_audit_summary
from agent.audit.result_consensus import (
    GameletOutcome,
    ResultAgreement,
    SignedResultAgreement,
    create_signed_result_agreement,
)
from agent.peer_result import (
    ResultExchangeError,
    _audit_bundle_hash,
    _parse_and_verify_audits,
    _series_id,
    accept_and_sign_result,
    agreement_from_series,
    exchange_series_result,
)
from agent.step0.declaration import DeclarationAgreement, PeerDeclaration, SignedDeclaration
from agent.step0.signing import generate_key_pair


def _zero_tokens():
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _audit(gamelet, keypair, game_id, config_hash, *, root=None):
    private, public = keypair
    return create_signed_audit_summary(
        AuditSummary(
            game_uid=game_id,
            gamelet=gamelet,
            transcript_root=root or f"root-{gamelet}",
            config_hash=config_hash,
            audit_status="PASSED",
            public_key_hex=public.hex(),
        ),
        private,
    )


def _fixture(tmp_path, *, counted=True, winner="cop"):
    config_hash = "c" * 64
    active_key = generate_key_pair()
    passive_key = generate_key_pair()
    series_id = f"series_{winner}"
    game_ids = [f"{series_id}_g{i:02d}" for i in range(1, 7)]
    active_audits = [
        _audit(i, active_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    passive_audits = [
        _audit(i, passive_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    active_points, passive_points = {
        "cop": (20, 5),
        "thief": (2, 10),
        "draw": (4, 4),
    }[winner]
    outcomes = [
        GameletOutcome(
            i,
            active_points,
            passive_points,
            winner,
            10,
            transcript_root=f"root-{i}",
            token_totals=_zero_tokens(),
        )
        for i in range(1, 7)
    ]
    local_step0 = {}
    remote_step0 = {}
    agreements = {}
    for game_id in game_ids:
        local = SignedDeclaration(
            PeerDeclaration(
                game_uid=game_id,
                group_id="LOCAL123",
                public_key_hex=passive_key[1].hex(),
            ),
            "local-signature",
        )
        remote = SignedDeclaration(
            PeerDeclaration(
                game_uid=game_id,
                group_id="REMOTE12",
                public_key_hex=active_key[1].hex(),
            ),
            "remote-signature",
        )
        local_step0[game_id] = local
        remote_step0[game_id] = remote
        agreements[game_id] = DeclarationAgreement.from_declarations(
            game_id,
            local.declaration.declaration_hash(),
            remote.declaration.declaration_hash(),
        )
    observed = {
        game_id: {
            "gamelet": i,
            "cop_score": active_points,
            "thief_score": passive_points,
            "winner": winner,
            "turns_played": 10,
        }
        for i, game_id in enumerate(game_ids, start=1)
    }
    orchestrator = MagicMock()
    orchestrator.send_report_via_gatekeeper.return_value = "delivery-id"
    runtime = SimpleNamespace(
        role="thief",
        games_dir=tmp_path,
        config_sha256=config_hash,
        counted_mode=counted,
        _signing_private_key=passive_key[0],
        _local_audit_summaries={a.summary.game_uid: a for a in passive_audits},
        _remote_audit_summaries={},
        _local_step0=local_step0,
        _remote_step0=remote_step0,
        _step0_agreements=agreements,
        _observed_gamelet_outcomes=observed,
        _adaptive_profile=ProtocolProfile.native(),
        _inbound_profile_hash="inbound-profile",
        orchestrator=orchestrator,
    )
    agreement = ResultAgreement(
        game_uid=series_id,
        gamelet_outcomes=outcomes,
        cop_total_score=active_points * 6,
        thief_total_score=passive_points * 6,
        series_winner=winner,
        counted_status=counted,
        both_audit_summaries_hash=_audit_bundle_hash(active_audits + passive_audits),
        token_totals=_zero_tokens(),
        timestamp_utc="2026-01-01T00:00:00Z",
    )
    message = SimpleNamespace(
        signed_result_agreement=create_signed_result_agreement(agreement, active_key[0]).to_dict(),
        signed_audit_summaries=[a.to_dict() for a in active_audits],
    )
    return SimpleNamespace(
        runtime=runtime,
        agreement=agreement,
        message=message,
        game_ids=game_ids,
        active_key=active_key,
        passive_key=passive_key,
        active_audits=active_audits,
        passive_audits=passive_audits,
    )


@pytest.mark.parametrize("winner", ["cop", "thief", "draw"])
def test_counted_passive_success_persists_evidence_ledger_and_report(tmp_path, winner) -> None:
    fx = _fixture(tmp_path, winner=winner)

    response = accept_and_sign_result(fx.runtime, fx.game_ids[-1], fx.message)

    assert response == {
        "ok": True,
        "signed_result_agreement": fx.runtime._signed_series_result.to_dict(),
        "report_delivery_id": "delivery-id",
    }
    artifact = tmp_path / f"result_agreement_{fx.agreement.game_uid}_passive.json"
    evidence = json.loads(artifact.read_text(encoding="utf-8"))["verification_evidence"]
    assert len(evidence["step0"]) == 6
    assert len(evidence["local_signed_audit_summaries"]) == 6
    assert evidence["adaptive_protocol_profile"]["profile_hash"]
    encoded = json.dumps(evidence, separators=(",", ":"))
    assert '"nonce":' not in encoded
    assert '"nonces":' not in encoded
    fx.runtime.orchestrator.record_match_in_ledger.assert_called_once()
    fx.runtime.orchestrator.send_report_via_gatekeeper.assert_called_once()


def test_result_helpers_reject_malformed_series_and_incomplete_data(tmp_path) -> None:
    fx = _fixture(tmp_path)
    with pytest.raises(ResultExchangeError, match="invalid gamelet"):
        _series_id("not-a-gamelet")
    assert _series_id(fx.game_ids[0]) == fx.agreement.game_uid
    with pytest.raises(ResultExchangeError, match="six gamelets"):
        agreement_from_series(fx.runtime, {"gamelets": []})
    bad = {
        "series_id": fx.agreement.game_uid,
        "series_winner": "cop",
        "cop_total": 0,
        "thief_total": 0,
        "ended_at": "now",
        "gamelets": [{"audit_ok": False}] * 6,
    }
    with pytest.raises(ResultExchangeError, match="audit did not pass"):
        agreement_from_series(fx.runtime, bad)

    fx.runtime._observed_gamelet_outcomes = {}
    response = accept_and_sign_result(fx.runtime, fx.game_ids[-1], fx.message)
    assert response["ok"] is False
    assert "independent outcome evidence is incomplete" in response["error"]


@pytest.mark.asyncio
async def test_active_exchange_writes_byte_identical_artifact(tmp_path, monkeypatch) -> None:
    fx = _fixture(tmp_path)
    fx.runtime.role = "cop"
    fx.runtime._remote_audit_summaries = {
        audit.summary.game_uid: audit for audit in fx.active_audits
    }
    fx.runtime._signing_private_key = fx.passive_key[0]
    for declaration in fx.runtime._remote_step0.values():
        declaration.declaration.public_key_hex = fx.active_key[1].hex()

    records = [
        {
            "game_id": game_id,
            "audit_ok": True,
            "cop_pts": 20,
            "thief_pts": 5,
            "winner": "cop",
            "final_step": 10,
            "token_totals": _zero_tokens(),
        }
        for game_id in fx.game_ids
    ]
    series_result = {
        "series_id": fx.agreement.game_uid,
        "gamelets": records,
        "cop_total": 120,
        "thief_total": 30,
        "series_winner": "cop",
        "ended_at": "2026-01-01T00:00:00Z",
        "token_totals": _zero_tokens(),
    }

    async def fake_call(_runtime, phase, message, protected):
        assert phase == "result_agreement"
        assert protected["result_hash"]
        incoming = SignedResultAgreement.from_dict(message["signed_result_agreement"])
        remote = create_signed_result_agreement(incoming.agreement, fx.active_key[0])
        return {"ok": True, "signed_result_agreement": remote.to_dict()}

    monkeypatch.setattr("agent.peer_turn_helpers._call_adapted_phase", fake_call)
    artifact = await exchange_series_result(fx.runtime, series_result)

    assert artifact["agreement"]["game_uid"] == fx.agreement.game_uid
    assert len(artifact["verification_evidence"]["remote_signed_audit_summaries"]) == 6
    assert (tmp_path / f"result_agreement_{fx.agreement.game_uid}.json").is_file()


@pytest.mark.asyncio
async def test_active_exchange_fails_closed_on_peer_rejection(tmp_path, monkeypatch) -> None:
    fx = _fixture(tmp_path)
    fx.runtime._remote_audit_summaries = {
        audit.summary.game_uid: audit for audit in fx.active_audits
    }
    records = [
        {
            "game_id": game_id,
            "audit_ok": True,
            "cop_pts": 20,
            "thief_pts": 5,
            "winner": "cop",
            "final_step": 10,
            "token_totals": _zero_tokens(),
        }
        for game_id in fx.game_ids
    ]
    result = {
        "series_id": fx.agreement.game_uid,
        "gamelets": records,
        "cop_total": 120,
        "thief_total": 30,
        "series_winner": "cop",
        "ended_at": "now",
        "token_totals": _zero_tokens(),
    }

    async def reject(*_args, **_kwargs):
        return {"ok": False, "error": "no"}

    monkeypatch.setattr("agent.peer_turn_helpers._call_adapted_phase", reject)
    with pytest.raises(ResultExchangeError, match="peer rejected"):
        await exchange_series_result(fx.runtime, result)


@pytest.mark.parametrize("case", ["length", "identity", "status", "config", "gamelets"])
def test_remote_audit_bundle_rejection_branches(tmp_path, case) -> None:
    fx = _fixture(tmp_path)
    payloads = [audit.to_dict() for audit in fx.active_audits]
    if case == "length":
        payloads.pop()
    elif case == "identity":
        fx.runtime._remote_step0.pop(fx.game_ids[0])
    else:
        changes = {
            "status": {"audit_status": "FAILED"},
            "config": {"config_hash": "wrong"},
            "gamelets": {"gamelet": 2},
        }[case]
        changed = create_signed_audit_summary(
            replace(fx.active_audits[0].summary, **changes), fx.active_key[0]
        )
        payloads[0] = changed.to_dict()
    with pytest.raises(ResultExchangeError):
        _parse_and_verify_audits(fx.runtime, payloads)


@pytest.mark.parametrize(
    "case",
    [
        "signer",
        "signature",
        "series",
        "outcomes",
        "local_length",
        "local_gamelets",
        "local_config",
        "bundle",
        "cop_total",
        "thief_total",
        "winner",
        "counted",
    ],
)
def test_passive_result_rejects_each_consensus_mismatch(tmp_path, case) -> None:
    fx = _fixture(tmp_path)
    agreement = fx.agreement
    if case == "signer":
        fx.runtime._remote_step0.pop(fx.game_ids[-1])
    elif case == "signature":
        fx.message.signed_result_agreement["signature_hex"] = "00"
    elif case == "series":
        agreement = replace(agreement, game_uid="different-series")
    elif case == "outcomes":
        agreement = replace(agreement, gamelet_outcomes=agreement.gamelet_outcomes[:-1])
    elif case == "local_length":
        fx.runtime._local_audit_summaries.pop(fx.game_ids[0])
    elif case in {"local_gamelets", "local_config"}:
        changes = {"gamelet": 2} if case == "local_gamelets" else {"config_hash": "wrong"}
        changed = create_signed_audit_summary(
            replace(fx.passive_audits[0].summary, **changes), fx.passive_key[0]
        )
        fx.runtime._local_audit_summaries[fx.game_ids[0]] = changed
    elif case == "bundle":
        agreement = replace(agreement, both_audit_summaries_hash="0" * 64)
    elif case == "cop_total":
        agreement = replace(agreement, cop_total_score=agreement.cop_total_score + 1)
    elif case == "thief_total":
        agreement = replace(agreement, thief_total_score=agreement.thief_total_score + 1)
    elif case == "winner":
        agreement = replace(agreement, series_winner="thief")
    elif case == "counted":
        agreement = replace(agreement, counted_status=False)
    if case not in {"signer", "signature"}:
        fx.message.signed_result_agreement = create_signed_result_agreement(
            agreement, fx.active_key[0]
        ).to_dict()
    response = accept_and_sign_result(fx.runtime, fx.game_ids[-1], fx.message)
    assert response["ok"] is False
