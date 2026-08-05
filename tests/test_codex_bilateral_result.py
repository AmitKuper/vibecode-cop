"""Production ResultAgreement must be six-gamelet, bilateral, and Step-0-bound."""

from __future__ import annotations

import json
from types import SimpleNamespace

from agent.audit.audit_summary import AuditSummary, create_signed_audit_summary
from agent.audit.result_consensus import (
    GameletOutcome,
    ResultAgreement,
    SignedResultAgreement,
    create_signed_result_agreement,
    verify_bilateral_consensus,
)
from agent.peer_result import (
    _audit_bundle_hash,
    _serializable_agreement_artifact,
    accept_and_sign_result,
)
from agent.step0.declaration import PeerDeclaration, SignedDeclaration
from agent.step0.signing import generate_key_pair


def _audit(gamelet, role_key, game_id, config_hash, status="PASSED"):
    private, public = role_key
    summary = AuditSummary(
        game_uid=game_id,
        gamelet=gamelet,
        transcript_root=f"root-{gamelet}",
        config_hash=config_hash,
        audit_status=status,
        public_key_hex=public.hex(),
    )
    return create_signed_audit_summary(summary, private)


def test_passive_signs_only_byte_identical_six_gamelet_result():
    config_hash = "c" * 64
    active_key = generate_key_pair()
    passive_key = generate_key_pair()
    series_id = "series_fixture"
    game_ids = [f"{series_id}_g{i:02d}" for i in range(1, 7)]
    active_audits = [
        _audit(i, active_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    passive_audits = [
        _audit(i, passive_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    remote_step0 = {
        game_id: SignedDeclaration(
            PeerDeclaration(game_uid=game_id, public_key_hex=active_key[1].hex()), ""
        )
        for game_id in game_ids
    }
    runtime = SimpleNamespace(
        _remote_step0=remote_step0,
        _local_audit_summaries={audit.summary.game_uid: audit for audit in passive_audits},
        _remote_audit_summaries={},
        _signing_private_key=passive_key[0],
        config_sha256=config_hash,
        counted_mode=False,
    )
    outcomes = [
        GameletOutcome(i, 20, 5, "cop", 10, transcript_root=f"root-{i}") for i in range(1, 7)
    ]
    agreement = ResultAgreement(
        game_uid=series_id,
        gamelet_outcomes=outcomes,
        cop_total_score=120,
        thief_total_score=30,
        series_winner="cop",
        counted_status=False,
        both_audit_summaries_hash=_audit_bundle_hash(active_audits + passive_audits),
    )
    active_signed = create_signed_result_agreement(agreement, active_key[0])
    message = SimpleNamespace(
        signed_result_agreement=active_signed.to_dict(),
        signed_audit_summaries=[a.to_dict() for a in active_audits],
    )

    response = accept_and_sign_result(runtime, game_ids[-1], message)

    assert response["ok"] is True
    passive_signed = SignedResultAgreement.from_dict(response["signed_result_agreement"])
    verify_bilateral_consensus(active_signed, passive_signed)


def test_result_agreement_artifact_serializes_nested_outcomes():
    private, _ = generate_key_pair()
    agreement = ResultAgreement(
        game_uid="series_fixture",
        gamelet_outcomes=[GameletOutcome(1, 20, 5, "cop", 4)],
    )
    local = create_signed_result_agreement(agreement, private)
    remote = create_signed_result_agreement(agreement, private)

    encoded = json.dumps(_serializable_agreement_artifact(local, remote))

    assert '"gamelet": 1' in encoded


def test_result_rejects_tampered_audit_bundle():
    config_hash = "c" * 64
    active_key = generate_key_pair()
    passive_key = generate_key_pair()
    game_ids = [f"series_fixture_g{i:02d}" for i in range(1, 7)]
    active_audits = [
        _audit(i, active_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    passive_audits = [
        _audit(i, passive_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    runtime = SimpleNamespace(
        _remote_step0={
            game_id: SignedDeclaration(
                PeerDeclaration(game_uid=game_id, public_key_hex=active_key[1].hex()), ""
            )
            for game_id in game_ids
        },
        _local_audit_summaries={a.summary.game_uid: a for a in passive_audits},
        _remote_audit_summaries={},
        _signing_private_key=passive_key[0],
        config_sha256=config_hash,
        counted_mode=False,
    )
    outcomes = [GameletOutcome(i, 2, 2, "draw", 35) for i in range(1, 7)]
    agreement = ResultAgreement(
        game_uid="series_fixture",
        gamelet_outcomes=outcomes,
        cop_total_score=12,
        thief_total_score=12,
        series_winner="draw",
        both_audit_summaries_hash=_audit_bundle_hash(active_audits + passive_audits),
    )
    signed = create_signed_result_agreement(agreement, active_key[0])
    payloads = [a.to_dict() for a in active_audits]
    payloads[0]["summary"]["audit_status"] = "FAILED"
    response = accept_and_sign_result(
        runtime,
        game_ids[-1],
        SimpleNamespace(signed_result_agreement=signed.to_dict(), signed_audit_summaries=payloads),
    )
    assert response["ok"] is False
    assert "audit signature" in response["error"]


def test_result_rejects_legitimately_signed_non_passing_local_audit():
    config_hash = "c" * 64
    active_key = generate_key_pair()
    passive_key = generate_key_pair()
    game_ids = [f"series_fixture_g{i:02d}" for i in range(1, 7)]
    active_audits = [
        _audit(i, active_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    passive_audits = [
        _audit(
            i,
            passive_key,
            game_id,
            config_hash,
            status="NOT_APPLICABLE" if i == 1 else "PASSED",
        )
        for i, game_id in enumerate(game_ids, start=1)
    ]
    runtime = SimpleNamespace(
        _remote_step0={
            game_id: SignedDeclaration(
                PeerDeclaration(game_uid=game_id, public_key_hex=active_key[1].hex()), ""
            )
            for game_id in game_ids
        },
        _local_audit_summaries={a.summary.game_uid: a for a in passive_audits},
        _remote_audit_summaries={},
        _signing_private_key=passive_key[0],
        config_sha256=config_hash,
        counted_mode=False,
    )
    outcomes = [GameletOutcome(i, 2, 2, "draw", 35) for i in range(1, 7)]
    agreement = ResultAgreement(
        game_uid="series_fixture",
        gamelet_outcomes=outcomes,
        cop_total_score=12,
        thief_total_score=12,
        series_winner="draw",
        both_audit_summaries_hash=_audit_bundle_hash(active_audits + passive_audits),
    )
    signed = create_signed_result_agreement(agreement, active_key[0])

    response = accept_and_sign_result(
        runtime,
        game_ids[-1],
        SimpleNamespace(
            signed_result_agreement=signed.to_dict(),
            signed_audit_summaries=[a.to_dict() for a in active_audits],
        ),
    )

    assert response["ok"] is False
    assert "local audit bundle contains a non-passing audit" in response["error"]


def test_counted_result_rejects_gamelet_not_independently_observed():
    config_hash = "c" * 64
    active_key = generate_key_pair()
    passive_key = generate_key_pair()
    series_id = "series_fixture"
    game_ids = [f"{series_id}_g{i:02d}" for i in range(1, 7)]
    active_audits = [
        _audit(i, active_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    passive_audits = [
        _audit(i, passive_key, game_id, config_hash) for i, game_id in enumerate(game_ids, start=1)
    ]
    outcomes = [
        GameletOutcome(i, 20, 5, "cop", 10, transcript_root=f"root-{i}") for i in range(1, 7)
    ]
    observed = {
        game_id: {
            "gamelet": i,
            "cop_score": 20,
            "thief_score": 5,
            "winner": "cop",
            "turns_played": 10,
        }
        for i, game_id in enumerate(game_ids, start=1)
    }
    observed[game_ids[2]]["winner"] = "thief"
    runtime = SimpleNamespace(
        _remote_step0={
            game_id: SignedDeclaration(
                PeerDeclaration(game_uid=game_id, public_key_hex=active_key[1].hex()), ""
            )
            for game_id in game_ids
        },
        _local_audit_summaries={a.summary.game_uid: a for a in passive_audits},
        _remote_audit_summaries={},
        _observed_gamelet_outcomes=observed,
        _signing_private_key=passive_key[0],
        config_sha256=config_hash,
        counted_mode=True,
    )
    agreement = ResultAgreement(
        game_uid=series_id,
        gamelet_outcomes=outcomes,
        cop_total_score=120,
        thief_total_score=30,
        series_winner="cop",
        counted_status=True,
        both_audit_summaries_hash=_audit_bundle_hash(active_audits + passive_audits),
    )
    signed = create_signed_result_agreement(agreement, active_key[0])

    response = accept_and_sign_result(
        runtime,
        game_ids[-1],
        SimpleNamespace(
            signed_result_agreement=signed.to_dict(),
            signed_audit_summaries=[a.to_dict() for a in active_audits],
        ),
    )

    assert response["ok"] is False
    assert "gamelet 3 disagrees with independent observation" in response["error"]
