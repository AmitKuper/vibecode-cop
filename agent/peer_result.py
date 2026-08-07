"""Bilateral byte-identical six-gamelet ResultAgreement exchange."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
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
import logging

from agent.mcp.messages import ActionMessage
from agent.peer_runtime_io import _now

logger = logging.getLogger(__name__)


class ResultExchangeError(RuntimeError):
    pass


_TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _validate_token_totals(totals: dict, label: str) -> None:
    if set(totals) != set(_TOKEN_KEYS):
        raise ResultExchangeError(f"{label} token totals are incomplete")
    if any(
        isinstance(totals[key], bool) or not isinstance(totals[key], int) for key in _TOKEN_KEYS
    ):
        raise ResultExchangeError(f"{label} token totals must be integers")
    if any(totals[key] < 0 for key in _TOKEN_KEYS):
        raise ResultExchangeError(f"{label} token totals must be non-negative")
    if totals["total_tokens"] != totals["prompt_tokens"] + totals["completion_tokens"]:
        raise ResultExchangeError(f"{label} total_tokens is inconsistent")


def _validate_counted_token_accounting(outcomes, series_totals: dict) -> None:
    for outcome in outcomes:
        _validate_token_totals(outcome.token_totals, f"gamelet {outcome.gamelet}")
    _validate_token_totals(series_totals, "series")
    for key in _TOKEN_KEYS:
        if sum(outcome.token_totals[key] for outcome in outcomes) != series_totals[key]:
            raise ResultExchangeError(f"series {key} does not equal gamelet totals")


def _serializable_agreement_artifact(local, remote) -> dict:
    """Return a JSON-native artifact, including nested gamelet outcomes."""
    return {
        "agreement": asdict(local.agreement),
        "local_signature_hex": local.signature_hex,
        "remote_signature_hex": remote.signature_hex,
    }


def _series_verification_evidence(runtime, local, remote) -> dict:
    """Collect public, independently verifiable series evidence; never include nonces."""
    game_ids = sorted(runtime._step0_agreements)
    return {
        "local_signed_result_agreement": local.to_dict(),
        "remote_signed_result_agreement": remote.to_dict(),
        "local_signed_audit_summaries": [
            runtime._local_audit_summaries[game_id].to_dict() for game_id in game_ids
        ],
        "remote_signed_audit_summaries": [
            runtime._remote_audit_summaries[game_id].to_dict() for game_id in game_ids
        ],
        "step0": [
            {
                "local_signed_declaration": runtime._local_step0[game_id].to_dict(),
                "remote_signed_declaration": runtime._remote_step0[game_id].to_dict(),
                "declaration_agreement": asdict(runtime._step0_agreements[game_id]),
            }
            for game_id in game_ids
        ],
        "adaptive_protocol_profile": (
            runtime._adaptive_profile.to_dict() if runtime._adaptive_profile is not None else None
        ),
        "inbound_profile_hash": runtime._inbound_profile_hash,
    }


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
        if runtime.counted_mode and (
            not signed.summary.declaration_agreement_hash
            or not signed.summary.protocol_profile_hash
            or not signed.summary.public_transition_root
            or not signed.summary.final_state_root
            or signed.summary.authoritative_final_step < 1
            or signed.summary.expected_steps != signed.summary.authoritative_final_step
            or signed.summary.verified_steps != signed.summary.authoritative_final_step
        ):
            raise ResultExchangeError(f"incomplete counted audit summary for {game_id}")
        if runtime.counted_mode:
            _validate_token_totals(signed.summary.token_totals, f"audit {game_id}")
        verified.append(signed)
    if sorted(s.summary.gamelet for s in verified) != list(range(1, 7)):
        raise ResultExchangeError("audit bundle is not exactly gamelets 1..6")
    return verified


def _validate_observed_outcomes(runtime, incoming, remote_audits) -> None:
    """Bind counted result fields to what the passive process independently saw."""
    if incoming.agreement.counted_status != runtime.counted_mode:
        raise ResultExchangeError("result counted status does not match runtime mode")
    if not runtime.counted_mode:
        return
    series_id = incoming.agreement.game_uid
    observed = {
        game_id: value
        for game_id, value in runtime._observed_gamelet_outcomes.items()
        if game_id.startswith(f"{series_id}_g")
    }
    if len(observed) != 6:
        raise ResultExchangeError(
            f"independent outcome evidence is incomplete: expected 6, got {len(observed)}"
        )
    audits_by_gamelet = {audit.summary.gamelet: audit for audit in remote_audits}
    for outcome in incoming.agreement.gamelet_outcomes:
        audit = audits_by_gamelet[outcome.gamelet]
        game_id = audit.summary.game_uid
        local = observed.get(game_id)
        if local is None:
            raise ResultExchangeError(f"missing independent outcome for {game_id}")
        expected = {
            "gamelet": outcome.gamelet,
            "cop_score": outcome.cop_score,
            "thief_score": outcome.thief_score,
            "winner": outcome.winner,
            "turns_played": outcome.turns_played,
            "final_state_root": outcome.final_state_root,
            "public_transition_root": outcome.public_transition_root,
        }
        if local != expected:
            raise ResultExchangeError(
                f"gamelet {outcome.gamelet} disagrees with independent observation"
            )
        if outcome.transcript_root != audit.summary.transcript_root:
            raise ResultExchangeError(
                f"gamelet {outcome.gamelet} transcript root is not audit-bound"
            )
        if outcome.final_state_root != audit.summary.final_state_root:
            raise ResultExchangeError(
                f"gamelet {outcome.gamelet} final state root is not audit-bound"
            )
        if outcome.public_transition_root != audit.summary.public_transition_root:
            raise ResultExchangeError(
                f"gamelet {outcome.gamelet} public transition root is not audit-bound"
            )
        expected_audit_outcome = {
            "cop": "cop_win",
            "thief": "thief_win",
            "draw": "draw",
        }.get(outcome.winner, "")
        if audit.summary.outcome != expected_audit_outcome or (
            audit.summary.cop_score,
            audit.summary.thief_score,
        ) != (outcome.cop_score, outcome.thief_score):
            raise ResultExchangeError(f"gamelet {outcome.gamelet} outcome/score is not audit-bound")


def agreement_from_series(runtime, series_result: dict) -> ResultAgreement:
    records = series_result.get("gamelets", [])
    if len(records) != 6:
        raise ResultExchangeError(f"result requires six gamelets, got {len(records)}")
    n_local = len(runtime._local_audit_summaries)
    n_remote = len(runtime._remote_audit_summaries)
    logger.info(
        "[ResultAgreement] Pre-flight: local_audit_summaries=%d remote_audit_summaries=%d",
        n_local, n_remote,
    )
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
                final_state_root=runtime._local_audit_summaries[
                    record["game_id"]
                ].summary.final_state_root,
                public_transition_root=runtime._local_audit_summaries[
                    record["game_id"]
                ].summary.public_transition_root,
                token_totals=dict(record.get("token_totals", {})),
            )
        )
    audits = list(runtime._local_audit_summaries.values()) + list(
        runtime._remote_audit_summaries.values()
    )
    if len(audits) != 12:
        local_ids = sorted(runtime._local_audit_summaries.keys())
        remote_ids = sorted(runtime._remote_audit_summaries.keys())
        expected_ids = sorted(r["game_id"] for r in records)
        missing_remote = [gid for gid in expected_ids if gid not in runtime._remote_audit_summaries]
        missing_local = [gid for gid in expected_ids if gid not in runtime._local_audit_summaries]
        logger.error(
            "[ResultAgreement] Audit bundle incomplete: local=%d remote=%d total=%d "
            "(need 12). missing_local=%s missing_remote=%s",
            len(local_ids), len(remote_ids), len(audits),
            missing_local, missing_remote,
        )
        raise ResultExchangeError(f"expected twelve bilateral audit summaries, got {len(audits)}")
    series_token_totals = dict(series_result.get("token_totals", {}))
    if runtime.counted_mode:
        _validate_counted_token_accounting(outcomes, series_token_totals)
    winner = series_result["series_winner"]
    protocol_hashes = {audit.summary.protocol_profile_hash for audit in audits}
    if len(protocol_hashes) != 1:
        local_hashes = {a.summary.protocol_profile_hash for a in runtime._local_audit_summaries.values()}
        remote_hashes = {a.summary.protocol_profile_hash for a in runtime._remote_audit_summaries.values()}
        logger.error(
            "[ResultAgreement] protocol_profile_hash mismatch: local_hashes=%s remote_hashes=%s",
            local_hashes, remote_hashes,
        )
        raise ResultExchangeError("audit summaries disagree on protocol profile hash")
    return ResultAgreement(
        game_uid=series_result["series_id"],
        gamelet_outcomes=outcomes,
        cop_total_score=int(series_result["cop_total"]),
        thief_total_score=int(series_result["thief_total"]),
        series_winner="draw" if winner == "tie" else winner,
        counted_status=runtime.counted_mode,
        token_totals=series_token_totals,
        config_hash=runtime.config_sha256,
        combined_protocol_profile_hash=protocol_hashes.pop(),
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
        series_prefix = _series_id(game_id)
        local_audits = [
            s for uid, s in runtime._local_audit_summaries.items()
            if uid.startswith(f"{series_prefix}_g")
        ]
        if len(local_audits) != 6:
            raise ResultExchangeError("local six-gamelet audit bundle is incomplete")
        if sorted(s.summary.gamelet for s in local_audits) != list(range(1, 7)):
            raise ResultExchangeError("local audit bundle is not exactly gamelets 1..6")
        if any(s.summary.audit_status != "PASSED" for s in local_audits):
            raise ResultExchangeError("local audit bundle contains a non-passing audit")
        if any(s.summary.config_hash != runtime.config_sha256 for s in local_audits):
            raise ResultExchangeError("local audit bundle contains a config mismatch")
        if runtime.counted_mode:
            local_by_gamelet = {summary.summary.gamelet: summary for summary in local_audits}
            for remote_summary in remote_audits:
                local_summary = local_by_gamelet[remote_summary.summary.gamelet]
                if (
                    local_summary.summary.consensus_fields_hash()
                    != remote_summary.summary.consensus_fields_hash()
                ):
                    raise ResultExchangeError(
                        f"audit consensus mismatch for gamelet {remote_summary.summary.gamelet}"
                    )
            if incoming.agreement.config_hash != runtime.config_sha256:
                raise ResultExchangeError("result config hash mismatch")
            protocol_hashes = {
                s.summary.protocol_profile_hash for s in local_audits + remote_audits
            }
            if protocol_hashes != {incoming.agreement.combined_protocol_profile_hash}:
                raise ResultExchangeError("result protocol profile hash mismatch")
        _validate_observed_outcomes(runtime, incoming, remote_audits)
        if runtime.counted_mode:
            _validate_counted_token_accounting(outcomes, incoming.agreement.token_totals)
        if _audit_bundle_hash(local_audits + remote_audits) != (
            incoming.agreement.both_audit_summaries_hash
        ):
            raise ResultExchangeError("bilateral audit bundle hash mismatch")
        if sum(o.cop_score for o in outcomes) != incoming.agreement.cop_total_score:
            raise ResultExchangeError("cop total is inconsistent")
        if sum(o.thief_score for o in outcomes) != incoming.agreement.thief_total_score:
            raise ResultExchangeError("thief total is inconsistent")
        if incoming.agreement.cop_total_score > incoming.agreement.thief_total_score:
            expected_winner = "cop"
        elif incoming.agreement.thief_total_score > incoming.agreement.cop_total_score:
            expected_winner = "thief"
        else:
            expected_winner = "draw"
        if incoming.agreement.series_winner != expected_winner:
            raise ResultExchangeError("series winner is inconsistent with totals")
        local = create_signed_result_agreement(incoming.agreement, runtime._signing_private_key)
        verify_bilateral_consensus(local, incoming)
        runtime._remote_audit_summaries.update({s.summary.game_uid: s for s in remote_audits})
        runtime._signed_series_result = local
        response = {"ok": True, "signed_result_agreement": local.to_dict()}
        if runtime.counted_mode:
            passive_artifact = {
                **_serializable_agreement_artifact(local, incoming),
                "verification_evidence": _series_verification_evidence(runtime, local, incoming),
            }
            passive_path = (
                Path(runtime.games_dir)
                / f"result_agreement_{incoming.agreement.game_uid}_passive.json"
            )
            passive_path.write_text(json.dumps(passive_artifact, indent=2), encoding="utf-8")
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
    logger.info(
        "[exchange_series_result] Starting: local_audits=%d remote_audits=%d gamelets=%d",
        len(runtime._local_audit_summaries),
        len(runtime._remote_audit_summaries),
        len(series_result.get("gamelets", [])),
    )
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
    artifact = _serializable_agreement_artifact(local, remote)
    artifact["verification_evidence"] = _series_verification_evidence(runtime, local, remote)
    path = Path(runtime.games_dir) / f"result_agreement_{agreement.game_uid}.json"
    path.write_text(json.dumps(artifact, indent=2))
    runtime._signed_series_result = local
    return artifact
