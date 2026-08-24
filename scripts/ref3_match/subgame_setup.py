"""Sub-game handshake: identity, session reset, greeting exchange, step-zero seal."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from league_artifacts.declaration import _hardware_spec

from ref3_match import gui_context, settled_row
from ref3_match.net import _poll_agreement
from ref3_match.runtime_cfg import _t
from ref3_match.setup_identity import build_identity
from ref3_match.setup_identity import print_refusal_diag as _print_refusal_diag


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
    series_label: str = "",
):
    """Exchange + verify greetings; seal step-0. Returns the handshake context dict."""

    from cop_worker.protocol.reference_v3 import (
        ReferenceV3Inbox,
        build_negotiation,
        reference_commit,
        verify_negotiation,
    )

    # Step-zero identity (rules 49/53) — built in setup_identity.build_identity.
    our_identity = build_identity(role, group_id, group_name, members, our_counted)
    our_commit = our_identity["github_commit"]
    # Fresh per-sub-game state: sealed records and the inbox must never leak across
    # sub-games (else step 1 of the next sub-game equivocates against the last one).
    settled_row.forget(in_session)  # a previous window's row must not answer for this one
    out_session.local_records = []
    out_session._local_records_by_step = {}
    out_session.sent_turns = []  # game-record capture is per-window, like the seals
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
        series_label=series_label or None,
    )
    # Stage our greeting on the INBOUND session first: a reply-dialect peer
    # (cosmos77) completes Step-0 from our negotiate ack alone, so any single
    # overlap suffices — no push-cadence-vs-handshake-budget lottery.
    if not hasattr(in_session, "staged_greetings"):
        in_session.staged_greetings = {}
    in_session.staged_greetings[sub_game] = greeting
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
        negotiated = verify_negotiation(greeting, theirs, series_label or None)
    except Exception as exc:
        _print_refusal_diag(sub_game, greeting, theirs, exc)
        raise
    print(
        f"[match] sg{sub_game} role={role} handshake OK vs {negotiated.opponent_group} "
        f"uid={negotiated.game_uid[:12]}"
    )
    gui_context.note_window(sub_game, negotiated.opponent_group, terms)
    # Step-0 sealed ON the wire: a fresh-nonce commitment of our identity (github_commit,
    # declaration_ref) that rides submit_audit as records[0] — matching anrbj666's g01 recipe
    # byte-for-byte. The peer's verify_audit rehashes it; step 0 is exempt from the played
    # binding (step >= 1 only), so it is a sealed record, not just the negotiate identity.
    sz_payload = {
        "declaration_ref": f"declaration_{negotiated.game_id}.json",
        "github_commit": our_commit,
        "group_id": group_id,
        "role": role,
        # The book wants a system spec in Step-0; peers read it off the sealed record
        # rather than the declaration file (najamjad flagged its absence 2026-08-14).
        "spec": _hardware_spec(),
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
