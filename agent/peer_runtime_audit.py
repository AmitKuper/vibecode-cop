"""PeerRuntime audit and game-end notification helpers."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from agent.mcp.messages import ActionMessage
from agent.peer_audit import load_opponent_commits, run_final_audit

logger = logging.getLogger(__name__)


async def do_final_audit(
    opponent_client,
    game_id: str,
    role: str,
    config_sha256: str,
    my_commits: dict,
    game_dir: Path,
    opponent_role: str,
    last_step: int,
    now_fn,
    *,
    gamelet: int = 0,
    runtime=None,
) -> tuple[bool, dict]:
    """Send FINAL_AUDIT to opponent, receive their nonces, verify locally.

    Performs bilateral AuditSummary exchange: each peer signs its audit result
    and verifies the opponent's signed summary for consensus.

    On the active (cop) side, advance the ProtocolCoordinator through
    on_audit_begin → on_final_audit_complete → on_done so that the SM
    reaches DONE rather than staying in STEP_VERIFIED indefinitely.
    """
    from agent.audit.audit_summary import (
        AuditSummary,
        SignedAuditSummary,
        create_signed_audit_summary,
        verify_audit_summary,
    )
    from agent.mcp.coordinator import get_coordinator
    from agent.step0.signing import generate_key_pair

    coord = get_coordinator()

    # Advance SM: STEP_VERIFIED → AUDITING (active side)
    coord.on_audit_begin(game_id, gamelet, role)

    my_nonces = {str(s): p["nonce"] for s, p in my_commits.items()}
    msg = ActionMessage(
        game_id=game_id,
        step=last_step,
        role=role,
        config_sha256=config_sha256,
        timestamp=now_fn(),
        phase="final_audit",
        nonces=my_nonces,
    )
    try:
        if runtime is not None and runtime.protocol_adapter is not None:
            from agent.peer_turn_helpers import _call_adapted_phase

            resp = await _call_adapted_phase(
                runtime,
                "final_audit",
                msg.to_dict(),
                {"nonces": my_nonces},
            )
        else:
            resp = await opponent_client.action(game_id, msg)
    except Exception as exc:
        logger.error(f"[PeerRuntime] FINAL_AUDIT call failed: {exc}")
        return False, {"error": str(exc)}

    opp_nonces_raw = resp.get("nonces", {})
    opp_nonces = {int(k): v for k, v in opp_nonces_raw.items()}
    audit_ok, details = run_final_audit(
        game_dir,
        game_id,
        opponent_role,
        opp_nonces,
        gamelet=max(1, gamelet),
        authoritative_final_step=last_step,
    )
    logger.info(f"[PeerRuntime/{role}] Final audit: ok={audit_ok} details={details}")

    if runtime is not None and audit_ok:
        try:
            runtime.orchestrator.get_journal(gamelet).seal_nonces(
                {int(step): payload["nonce"] for step, payload in my_commits.items()},
                opp_nonces,
                expected_steps=last_step,
            )
        except Exception as exc:
            details["journal_seal_error"] = str(exc)
            details["audit_status"] = "FAILED"
            audit_ok = False

    # Create and sign own AuditSummary
    if runtime is not None:
        priv_key = runtime._signing_private_key
        pub_key = runtime._signing_public_key
        signing_key_id = runtime._signing_key_id
        from agent.mcp.crypto import canonical_domain_state_root, combined_protocol_hash

        local_step0 = runtime._local_step0.get(game_id)
        remote_step0 = runtime._remote_step0.get(game_id)
        declaration_hash = local_step0.declaration.declaration_hash() if local_step0 else ""
        declaration_agreement_hash = getattr(
            runtime._step0_agreements.get(game_id), "agreement_hash", ""
        )
        protocol_profile_hash = combined_protocol_hash(
            getattr(getattr(local_step0, "declaration", None), "adapter_mapping_hash", ""),
            getattr(getattr(remote_step0, "declaration", None), "adapter_mapping_hash", ""),
        )
        transcript_root = runtime.orchestrator.get_journal(gamelet).transcript_root()
        local_final_state_hash = canonical_domain_state_root(runtime._domain_state, config_sha256)
        transition = runtime._last_transition_result
    else:
        priv_key, pub_key = generate_key_pair()
        signing_key_id = "legacy-ephemeral"
        declaration_hash = ""
        declaration_agreement_hash = ""
        protocol_profile_hash = ""
        transcript_root = ""
        local_final_state_hash = ""
        transition = None
    pub_hex = pub_key.hex()
    audit_status = details.get("audit_status", "NOT_APPLICABLE")
    my_summary = AuditSummary(
        game_uid=game_id,
        gamelet=gamelet,
        transcript_root=transcript_root,
        declaration_hash=declaration_hash,
        declaration_agreement_hash=declaration_agreement_hash,
        config_hash=config_sha256,
        protocol_profile_hash=protocol_profile_hash,
        public_transition_root=(runtime._public_transition_root if runtime is not None else ""),
        authoritative_final_step=last_step,
        expected_steps=last_step,
        verified_steps=sum(1 for k, v in details.items() if k.startswith("step_") and v == "ok"),
        audit_status=audit_status,
        mismatch_evidence="" if audit_ok else str(details),
        local_final_state_hash=local_final_state_hash,
        final_state_root=local_final_state_hash,
        outcome=(transition.outcome.value if transition is not None else ""),
        cop_score=(transition.cop_score if transition is not None else 0),
        thief_score=(transition.thief_score if transition is not None else 0),
        token_totals={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        signing_key_id=signing_key_id,
        public_key_hex=pub_hex,
    )
    my_signed = create_signed_audit_summary(my_summary, priv_key)
    details["my_audit_summary_hash"] = my_summary.summary_hash()
    details["my_signed_summary"] = my_signed.to_dict()
    if runtime is not None:
        runtime._local_audit_summaries[game_id] = my_signed

    # Verify opponent's SignedAuditSummary if provided
    opp_summary_payload = resp.get("signed_audit_summary")
    if opp_summary_payload:
        try:
            if isinstance(opp_summary_payload, str):
                opp_summary_payload = json.loads(opp_summary_payload)
            opp_signed = SignedAuditSummary.from_dict(opp_summary_payload)
            expected_key = None
            if runtime is not None:
                remote_step0 = runtime._remote_step0.get(game_id)
                if remote_step0 is None and runtime.counted_mode:
                    raise ValueError("missing remote Step-0 identity")
                if remote_step0 is not None:
                    expected_key = bytes.fromhex(remote_step0.declaration.public_key_hex)
            opp_valid = verify_audit_summary(opp_signed, expected_key)
            opp_valid = opp_valid and opp_signed.summary.game_uid == game_id
            opp_valid = opp_valid and opp_signed.summary.gamelet == gamelet
            if runtime is not None:
                opp_valid = opp_valid and opp_signed.summary.config_hash == config_sha256
                opp_valid = opp_valid and opp_signed.summary.audit_status == "PASSED"
                if runtime.counted_mode:
                    opp_valid = opp_valid and (
                        opp_signed.summary.consensus_fields_hash()
                        == my_summary.consensus_fields_hash()
                    )
            details["opponent_audit_summary_hash"] = opp_signed.summary.summary_hash()
            details["opponent_audit_verified"] = opp_valid
            details["opponent_audit_status"] = opp_signed.summary.audit_status
            if not opp_valid:
                logger.warning("[PeerRuntime/%s] Opponent AuditSummary is not passing", role)
                audit_ok = False
            elif runtime is not None:
                runtime._remote_audit_summaries[game_id] = opp_signed
        except Exception as exc:
            logger.warning("[PeerRuntime/%s] Failed to parse opponent AuditSummary: %s", role, exc)
            details["opponent_audit_parse_error"] = str(exc)
            audit_ok = False
    elif runtime is not None and runtime.counted_mode:
        details["opponent_audit_parse_error"] = "missing signed audit summary"
        audit_ok = False

    if audit_ok:
        # Advance SM: AUDITING → RESULT_AGREEMENT.  DONE is authorized only
        # after the bilateral byte-identical ResultAgreement.
        coord.on_final_audit_complete(game_id, gamelet, role)
    else:
        coord.on_technical_loss(game_id, gamelet, role, reason="audit_failed")

    return audit_ok, details


async def notify_game_end(
    opponent_client,
    game_id: str,
    role: str,
    config_sha256: str,
    step: int,
    winner: str,
    now_fn,
    *,
    runtime=None,
) -> dict:
    """Notify opponent that game has ended."""
    msg = ActionMessage(
        game_id=game_id,
        step=step,
        role=role,
        config_sha256=config_sha256,
        timestamp=now_fn(),
        phase="game_end",
        reason=winner,
    )
    try:
        if runtime is not None and runtime.protocol_adapter is not None:
            from agent.peer_turn_helpers import _call_adapted_phase

            response = await _call_adapted_phase(
                runtime,
                "game_end",
                msg.to_dict(),
                {"winner": winner, "reason": winner},
            )
        else:
            response = await opponent_client.action(game_id, msg)
        if not response.get("ok"):
            raise RuntimeError(f"peer rejected game_end: {response}")
        return response
    except Exception as exc:
        if runtime is not None and runtime.counted_mode:
            raise RuntimeError(f"COUNTED game_end notification failed: {exc}") from exc
        logger.warning(f"[PeerRuntime] game_end notification failed: {exc}")
        return {"ok": False, "error": str(exc)}


def count_opponent_commits(game_dir: Path) -> int:
    return len(load_opponent_commits(game_dir))
