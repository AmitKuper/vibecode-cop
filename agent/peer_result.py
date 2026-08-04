"""Bilateral byte-identical six-gamelet ResultAgreement exchange."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent.audit.audit_summary import SignedAuditSummary, verify_audit_summary
from agent.audit.result_consensus import (
    GameletOutcome,
    ResultAgreement,
    SignedResultAgreement,
    create_signed_result_agreement,
    verify_bilateral_consensus,
    verify_result_agreement_signature,
)
from agent.mcp.messages import ActionMessage
from agent.peer_runtime_io import _now


class ResultExchangeError(RuntimeError):
    pass


def _series_id(game_id: str) -> str:
    prefix, marker, suffix = game_id.rpartition("_g")
    if not marker or not suffix.isdigit():
        raise ResultExchangeError(f"invalid gamelet id {game_id!r}")
    return prefix


def _audit_bundle_hash(summaries: list[SignedAuditSummary]) -> str:
    hashes = sorted(summary.summary.summary_hash() for summary in summaries)
    return hashlib.sha256("".join(hashes).encode()).hexdigest()


def _parse_and_verify_audits(runtime, payloads: list[dict]) -> list[SignedAuditSummary]:
    if len(payloads) != 6:
        raise ResultExchangeError(f"expected six peer audit summaries, got {len(payloads)}")
    verified: list[SignedAuditSummary] = []
    for payload in payloads:
        signed = SignedAuditSummary.from_dict(payload)
        game_id = signed.summary.game_uid
        remote_decl = runtime._remote_step0.get(game_id)
        if remote_decl is None:
            raise ResultExchangeError(f"missing Step-0 identity for {game_id}")
        key = bytes.fromhex(remote_decl.declaration.public_key_hex)
        if not verify_audit_summary(signed, key):
            raise ResultExchangeError(f"invalid audit signature for {game_id}")
        if signed.summary.audit_status != "PASSED":
            raise ResultExchangeError(f"non-passing audit for {game_id}")
        if signed.summary.config_hash != runtime.config_sha256:
            raise ResultExchangeError(f"audit config mismatch for {game_id}")
        verified.append(signed)
    if sorted(s.summary.gamelet for s in verified) != list(range(1, 7)):
        raise ResultExchangeError("audit bundle is not exactly gamelets 1..6")
    return verified


def agreement_from_series(runtime, series_result: dict) -> ResultAgreement:
    records = series_result.get("gamelets", [])
    if len(records) != 6:
        raise ResultExchangeError(f"result requires six gamelets, got {len(records)}")
    outcomes = []
    for index, record in enumerate(records, start=1):
        if record.get("audit_ok") is not True:
            raise ResultExchangeError(f"gamelet {index} audit did not pass")
        outcomes.append(
            GameletOutcome(
                gamelet=index,
                cop_score=int(record["cop_pts"]),
                thief_score=int(record["thief_pts"]),
                winner=record["winner"],
                turns_played=int(record.get("final_step") or 0),
                transcript_root=runtime._local_audit_summaries[
                    record["game_id"]
                ].summary.transcript_root,
            )
        )
    audits = list(runtime._local_audit_summaries.values()) + list(
        runtime._remote_audit_summaries.values()
    )
    if len(audits) != 12:
        raise ResultExchangeError(f"expected twelve bilateral audit summaries, got {len(audits)}")
    winner = series_result["series_winner"]
    return ResultAgreement(
        game_uid=series_result["series_id"],
        gamelet_outcomes=outcomes,
        cop_total_score=int(series_result["cop_total"]),
        thief_total_score=int(series_result["thief_total"]),
        series_winner="draw" if winner == "tie" else winner,
        counted_status=runtime.counted_mode,
        both_audit_summaries_hash=_audit_bundle_hash(audits),
        timestamp_utc=series_result["ended_at"],
    )


def accept_and_sign_result(runtime, game_id: str, message) -> dict:
    """Passive peer verifies all evidence and signs the exact received bytes."""
    try:
        incoming = SignedResultAgreement.from_dict(message.signed_result_agreement)
        remote_decl = runtime._remote_step0.get(game_id)
        if remote_decl is None:
            raise ResultExchangeError("missing result signer's Step-0 identity")
        remote_key = bytes.fromhex(remote_decl.declaration.public_key_hex)
        if not verify_result_agreement_signature(incoming, remote_key):
            raise ResultExchangeError("result signature is not bound to Step-0")
        if incoming.agreement.game_uid != _series_id(game_id):
            raise ResultExchangeError("series identifier mismatch")
        outcomes = incoming.agreement.gamelet_outcomes
        if len(outcomes) != 6 or [o.gamelet for o in outcomes] != list(range(1, 7)):
            raise ResultExchangeError("result is not exactly gamelets 1..6")
        remote_audits = _parse_and_verify_audits(runtime, message.signed_audit_summaries or [])
        local_audits = list(runtime._local_audit_summaries.values())
        if len(local_audits) != 6:
            raise ResultExchangeError("local six-gamelet audit bundle is incomplete")
        if _audit_bundle_hash(local_audits + remote_audits) != (
            incoming.agreement.both_audit_summaries_hash
        ):
            raise ResultExchangeError("bilateral audit bundle hash mismatch")
        if sum(o.cop_score for o in outcomes) != incoming.agreement.cop_total_score:
            raise ResultExchangeError("cop total is inconsistent")
        if sum(o.thief_score for o in outcomes) != incoming.agreement.thief_total_score:
            raise ResultExchangeError("thief total is inconsistent")
        local = create_signed_result_agreement(incoming.agreement, runtime._signing_private_key)
        verify_bilateral_consensus(local, incoming)
        runtime._remote_audit_summaries.update({s.summary.game_uid: s for s in remote_audits})
        runtime._signed_series_result = local
        response = {"ok": True, "signed_result_agreement": local.to_dict()}
        if runtime.counted_mode:
            step0 = runtime._step0_agreements[game_id]
            runtime.orchestrator.record_match_in_ledger(
                opponent_id=remote_decl.declaration.group_id,
                match_id=incoming.agreement.game_uid,
                counted=True,
                declaration_hash=step0.agreement_hash,
                result_hash=incoming.agreement.agreement_hash(),
                both_result_signatures=[incoming.signature_hex, local.signature_hex],
            )
            response["report_delivery_id"] = runtime.orchestrator.send_report_via_gatekeeper(
                idempotency_key=f"{incoming.agreement.game_uid}_{runtime.role}",
                game_id=incoming.agreement.game_uid,
                result_json=json.dumps(incoming.to_dict(), sort_keys=True),
            )
        return response
    except Exception as exc:
        return {"ok": False, "error": f"ResultAgreement rejected: {exc}"}


async def exchange_series_result(runtime, series_result: dict) -> dict:
    agreement = agreement_from_series(runtime, series_result)
    local = create_signed_result_agreement(agreement, runtime._signing_private_key)
    last_game_id = series_result["gamelets"][-1]["game_id"]
    message = ActionMessage(
        game_id=last_game_id,
        step=int(series_result["gamelets"][-1].get("final_step") or 0),
        role=runtime.role,
        config_sha256=runtime.config_sha256,
        timestamp=_now(),
        phase="result_agreement",
        signed_result_agreement=local.to_dict(),
        signed_audit_summaries=[
            runtime._local_audit_summaries[r["game_id"]].to_dict()
            for r in series_result["gamelets"]
        ],
    )
    from agent.peer_turn_helpers import _call_adapted_phase

    response = await _call_adapted_phase(
        runtime,
        "result_agreement",
        message.to_dict(),
        {
            "result_hash": agreement.agreement_hash(),
            "signed_agreement": local.to_dict(),
        },
    )
    if not response.get("ok") or not response.get("signed_result_agreement"):
        raise ResultExchangeError(f"peer rejected ResultAgreement: {response}")
    remote = SignedResultAgreement.from_dict(response["signed_result_agreement"])
    remote_decl = runtime._remote_step0[last_game_id]
    remote_key = bytes.fromhex(remote_decl.declaration.public_key_hex)
    if not verify_result_agreement_signature(remote, remote_key):
        raise ResultExchangeError("peer result signature is not bound to Step-0")
    verify_bilateral_consensus(local, remote)
    artifact = {
        "agreement": local.agreement.__dict__,
        "local_signature_hex": local.signature_hex,
        "remote_signature_hex": remote.signature_hex,
    }
    path = Path(runtime.games_dir) / f"result_agreement_{agreement.game_uid}.json"
    path.write_text(json.dumps(artifact, indent=2, default=lambda o: o.__dict__))
    runtime._signed_series_result = local
    return artifact
