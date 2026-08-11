"""Sub-game handshake: identity, session reset, greeting exchange, step-zero seal."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from ref3_match.net import _poll_agreement
from ref3_match.runtime_cfg import REPO_ROOT, _git_head, _t


def _print_refusal_diag(sub_game: int, greeting: dict, theirs: dict, exc: Exception) -> None:
    """A refusal is only actionable if it names the DIFF, not just the rule."""
    t_terms = theirs.get("terms") if isinstance(theirs.get("terms"), dict) else {}
    ours_terms = greeting["terms"]
    key_diff = sorted(set(ours_terms) ^ set(t_terms))
    val_diff = {
        k: (ours_terms.get(k), t_terms.get(k))
        for k in ours_terms
        if k in t_terms and ours_terms[k] != t_terms[k]
    }
    print(f"[match] sg{sub_game} HANDSHAKE REFUSED: {exc}")
    print(f"[diag ] terms key diff (ours^theirs): {key_diff or 'none'}")
    print(f"[diag ] terms value diff (ours vs theirs): {val_diff or 'none'}")
    print(
        f"[diag ] locks ours scent={greeting.get('scent_model_sha256', '')[:12]} "
        f"wire={greeting.get('wire_shape_sha256', '')[:12]} | theirs "
        f"scent={str(theirs.get('scent_model_sha256'))[:12]} "
        f"wire={str(theirs.get('wire_shape_sha256'))[:12]}"
    )
    print(
        f"[diag ] uid ours={greeting.get('game_uid')} theirs={theirs.get('game_uid')} "
        f"role ours={greeting.get('role')} theirs={theirs.get('role')} "
        f"sub_game ours={sub_game} theirs={theirs.get('sub_game_number')}"
    )


async def _handshake(
    out_session,
    in_session,
    *,
    role: str,
    sub_game: int,
    group_id: str,
    group_name: str,
    terms: dict,
    members: list | None,
    our_counted: int,
    scent_model: str,
    declared_opponent_group: str | None,
):
    """Exchange + verify greetings; seal step-0. Returns the handshake context dict."""
    from ref3_artifacts import OUR_MCP, OUR_REPOS

    from cop_worker.protocol.reference_v3 import (
        ReferenceV3Inbox,
        build_negotiation,
        reference_commit,
        verify_negotiation,
    )

    # Our step-zero identity on the wire (rules 49/53): repos, per-role github_commit,
    # counted count, members — so the peer records what we actually declare.
    our_repo = REPO_ROOT if role == "police" else REPO_ROOT.parent / "vibecode-thief"
    our_commit = _git_head(our_repo)
    our_identity = {
        "group_id": group_id,
        "group_name": group_name,
        # Honest declaration: movement is the trained role-specific RL policy; the verbal layer
        # is template-generated (no language model is called during play, so no LLM tokens are
        # consumed). The book forbids letting a model decide movement, and hints provably cannot
        # affect ours — local_obs_to_tensor never reads last_hint.
        "llm_model": "none (template hints; role-specific-recurrent-policy movement)",
        "mcp_servers": OUR_MCP,
        "repos": OUR_REPOS,
        "members": members or [],
        "github_commit": our_commit,
        "counted_games_played": our_counted,
    }
    # Fresh per-sub-game state: sealed records and the inbox must never leak across
    # sub-games (else step 1 of the next sub-game equivocates against the last one).
    out_session.local_records = []
    out_session._local_records_by_step = {}
    in_session.turns = ReferenceV3Inbox(window=_t("reorder_window", 4))
    in_session.turn_messages.clear()
    in_session.expected_turn_sender = None
    in_session.audits.clear()  # drain stale end-of-game payloads from prior sub-games
    in_session.controls.clear()
    started_at = datetime.now(UTC).isoformat()
    nonce = secrets.token_hex(16)
    # Declare our derived game_uid ONLY when the opponent's group_id is actually known
    # (configured pairing, or learned from sub-game 1's verified greeting). Kit §7.3:
    # both declare and differ → refuse; omission never refuses. Formula parity is pinned.
    greeting = build_negotiation(
        terms=terms,
        nonce=nonce,
        group_id=group_id,
        group_name=group_name,
        role=role,
        sub_game_number=sub_game,
        identity=our_identity,
        opponent_group=declared_opponent_group,
        scent_model=scent_model,
    )
    await out_session.send_negotiation(greeting)
    # Match the greeting by sub_game_number (not FIFO) — the peer's re-dials pile up.
    theirs = await _poll_agreement(
        in_session.agreements, sub_game, timeout=_t("agreement_poll_sec", 300.0)
    )
    opp_identity = theirs.get("identity") or {}  # their declared repos/commit/counted (rules 49/53)
    print(
        f"[match] sg{sub_game} peer greeting "
        f"sub_game={theirs.get('sub_game_number')} role={theirs.get('role')}"
    )
    try:
        negotiated = verify_negotiation(greeting, theirs)
    except Exception as exc:
        _print_refusal_diag(sub_game, greeting, theirs, exc)
        raise
    print(
        f"[match] sg{sub_game} role={role} handshake OK vs {negotiated.opponent_group} "
        f"uid={negotiated.game_uid[:12]}"
    )
    # Step-0 sealed ON the wire: a fresh-nonce commitment of our identity (github_commit,
    # declaration_ref) that rides submit_audit as records[0] — matching anrbj666's g01 recipe
    # byte-for-byte. The peer's verify_audit rehashes it; step 0 is exempt from the played
    # binding (step >= 1 only), so it is a sealed record, not just the negotiate identity.
    sz_payload = {
        "declaration_ref": f"declaration_{negotiated.game_id}.json",
        "github_commit": our_commit,
        "group_id": group_id,
        "role": role,
        "step": 0,
        "sub_game_number": sub_game,
        "type": "step_zero",
    }
    sz_nonce = secrets.token_hex(16)
    step_zero_record = {
        "payload": sz_payload,
        "nonce": sz_nonce,
        "commit": reference_commit(sz_payload, sz_nonce),
    }
    out_session.local_records.append(step_zero_record)  # records[0], sent in submit_audit
    out_session._local_records_by_step[0] = step_zero_record
    return {
        "negotiated": negotiated,
        "opp_identity": opp_identity,
        "our_commit": our_commit,
        "started_at": started_at,
    }
