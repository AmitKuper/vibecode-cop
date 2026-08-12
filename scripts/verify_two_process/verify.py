"""Independent verification of the artifacts produced by the acceptance run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from verify_two_process.util import COP_REPO, _contains_private_nonce_key, _sha256
from verify_two_process.verify_ledgers import _verify_ledgers_and_mail


def _verify_artifacts(output: Path, cop_sha: str, thief_sha: str) -> dict:
    if str(COP_REPO) not in sys.path:
        sys.path.insert(0, str(COP_REPO))
    from agent.audit.audit_summary import SignedAuditSummary, verify_audit_summary
    from agent.audit.result_consensus import (
        SignedResultAgreement,
        verify_bilateral_consensus,
        verify_result_agreement_signature,
    )
    from agent.step0.declaration import SignedDeclaration
    from agent.step0.signing import verify

    active_paths = list((output / "cop").glob("result_agreement_series_*.json"))
    passive_paths = list((output / "thief").glob("result_agreement_series_*_passive.json"))
    if len(active_paths) != 1 or len(passive_paths) != 1:
        raise RuntimeError(
            f"expected one active/passive agreement, got {len(active_paths)}/{len(passive_paths)}"
        )
    active_path, passive_path = active_paths[0], passive_paths[0]
    active = json.loads(active_path.read_text(encoding="utf-8"))
    passive = json.loads(passive_path.read_text(encoding="utf-8"))
    evidence = active["verification_evidence"]
    steps = evidence["step0"]
    if len(steps) != 6:
        raise RuntimeError(f"expected six Step-0 evidence pairs, got {len(steps)}")

    local_keys: dict[str, bytes] = {}
    remote_keys: dict[str, bytes] = {}
    local_profile_hashes: set[str] = set()
    remote_profile_hashes: set[str] = set()
    for item in steps:
        local = SignedDeclaration.from_dict(item["local_signed_declaration"])
        remote = SignedDeclaration.from_dict(item["remote_signed_declaration"])
        for signed, expected_sha in ((local, cop_sha), (remote, thief_sha)):
            declaration = signed.declaration
            public = bytes.fromhex(declaration.public_key_hex)
            signature = bytes.fromhex(signed.signature_hex)
            if not verify(public, declaration.canonical_bytes(), signature):
                raise RuntimeError(f"invalid Step-0 signature for {declaration.game_uid}")
            if declaration.git_sha != expected_sha:
                raise RuntimeError(
                    f"Step-0 git SHA mismatch for {declaration.model_role}: "
                    f"{declaration.git_sha} != {expected_sha}"
                )
        game_id = local.declaration.game_uid
        if remote.declaration.game_uid != game_id:
            raise RuntimeError("Step-0 peers disagree on game UID")
        local_keys[game_id] = bytes.fromhex(local.declaration.public_key_hex)
        remote_keys[game_id] = bytes.fromhex(remote.declaration.public_key_hex)
        local_profile_hashes.add(local.declaration.adapter_mapping_hash)
        remote_profile_hashes.add(remote.declaration.adapter_mapping_hash)
    if len(local_profile_hashes) != 1 or len(remote_profile_hashes) != 1:
        raise RuntimeError("adaptive profile changed during the counted series")

    local_audits = [
        SignedAuditSummary.from_dict(item) for item in evidence["local_signed_audit_summaries"]
    ]
    remote_audits = [
        SignedAuditSummary.from_dict(item) for item in evidence["remote_signed_audit_summaries"]
    ]
    if len(local_audits) != 6 or len(remote_audits) != 6:
        raise RuntimeError("bilateral audit evidence is not exactly 6+6 summaries")
    for summaries, keys in ((local_audits, local_keys), (remote_audits, remote_keys)):
        for signed in summaries:
            summary = signed.summary
            if summary.audit_status != "PASSED":
                raise RuntimeError(f"non-passing audit for {summary.game_uid}")
            if not verify_audit_summary(signed, keys[summary.game_uid]):
                raise RuntimeError(f"invalid audit signature for {summary.game_uid}")

    local_result = SignedResultAgreement.from_dict(evidence["local_signed_result_agreement"])
    remote_result = SignedResultAgreement.from_dict(evidence["remote_signed_result_agreement"])
    last_game_id = sorted(local_keys)[-1]
    if not verify_result_agreement_signature(local_result, local_keys[last_game_id]):
        raise RuntimeError("active ResultAgreement signature is not Step-0-bound")
    if not verify_result_agreement_signature(remote_result, remote_keys[last_game_id]):
        raise RuntimeError("passive ResultAgreement signature is not Step-0-bound")
    verify_bilateral_consensus(local_result, remote_result)
    if active["agreement"] != passive["agreement"]:
        raise RuntimeError("active and passive agreement artifacts differ")
    agreement = local_result.agreement
    if len(agreement.gamelet_outcomes) != 6:
        raise RuntimeError("ResultAgreement is not exactly six gamelets")
    required_tokens = {"prompt_tokens", "completion_tokens", "total_tokens"}
    if set(agreement.token_totals) != required_tokens:
        raise RuntimeError("series token totals missing from ResultAgreement")
    if any(set(outcome.token_totals) != required_tokens for outcome in agreement.gamelet_outcomes):
        raise RuntimeError("gamelet token totals missing from ResultAgreement")
    if _contains_private_nonce_key(active):
        raise RuntimeError("public result evidence contains private nonce-value keys")

    ledgers, peer_ledgers, ledger_consensus_sha256 = _verify_ledgers_and_mail(output)

    return {
        "status": "PASS",
        "series_id": agreement.game_uid,
        "gamelets": 6,
        "step0_signatures_verified": 12,
        "audit_signatures_verified": 12,
        "result_signatures_verified": 2,
        "cop_git_sha": cop_sha,
        "thief_git_sha": thief_sha,
        "active_profile_hash": next(iter(local_profile_hashes)),
        "passive_profile_hash": next(iter(remote_profile_hashes)),
        "agreement_hash": agreement.agreement_hash(),
        "active_artifact": str(active_path),
        "active_artifact_sha256": _sha256(active_path),
        "passive_artifact": str(passive_path),
        "passive_artifact_sha256": _sha256(passive_path),
        "cop_ledger_sha256": _sha256(ledgers[0]),
        "thief_ledger_sha256": _sha256(peer_ledgers[0]),
        "ledger_consensus_sha256": ledger_consensus_sha256,
        "fake_gmail_records": 2,
        "real_gmail_status": "EXTERNAL_PENDING",
        "public_nonce_value_keys": 0,
        "token_totals": agreement.token_totals,
    }
