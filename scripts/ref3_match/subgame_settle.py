"""Sub-game settlement: mutual audit verification, record collection, result summary."""

from __future__ import annotations

from datetime import UTC, datetime

from ref3_match import gui_context, settled_row
from ref3_match.net import _poll_deque
from ref3_match.runtime_cfg import _t


def _refine_disputed_trail(opp_records, settled_caught_cell, sub_game: int):
    """Audit-time refinement of a settled caught=true: the conceded/answered cell must end
    the thief's REVEALED trail. Two conforming trail shapes (live finding, najamjad
    2026-08-13, 3/3 capture windows): kit-style concession records carry ONE post-answer
    move, so the caught cell legitimately sits at trail[-2] with the concession record
    (the one answering caught) as trail[-1]. Degradation contract (SPEC §3.1): a peer
    whose payloads carry no parseable position is fully conforming — note, never accuse;
    only a trail that contradicts BOTH shapes marks the capture disputed.
    """
    _trail = [
        (int(p["step"]), list(p["position"]))
        for p in ((r.get("payload") or {}) for r in opp_records)
        if isinstance(p.get("step"), int)
        and p.get("step") >= 1
        and isinstance(p.get("position"), (list, tuple))
        and len(p.get("position")) == 2
    ]
    if not _trail:
        return None
    cell = list(settled_caught_cell)
    ordered = sorted(_trail)
    if list(ordered[-1][1]) == cell:
        return None  # strict shape: trail ends on the caught cell
    if len(ordered) >= 2 and list(ordered[-2][1]) == cell:
        return None  # concession shape: one post-answer record after the caught cell
    print(
        f"[match] sg{sub_game} audit: caught cell {cell} does not end the revealed "
        f"trail (final={ordered[-1][1]}) — recording disputed"
    )
    return {
        "cell": cell,
        "kind": "trail_end_mismatch",
        "revealed_final": list(ordered[-1][1]),
    }


async def _settle(
    out_session,
    in_session,
    *,
    role: str,
    sub_game: int,
    hs: dict,
    opponent_group_hint: str,
    rl_moves: list,
    captured: bool,
    disputed_capture,
    settled_caught_cell,
) -> dict:
    """Verify the peer's audit and assemble the sub-game result row."""
    from cop_worker.protocol.reference_v3 import ReferenceV3Inbox, verify_audit

    their_audit = await _poll_deque(
        in_session.audits, timeout=_t("audit_poll_sec", 300.0), label="audit"
    )
    ok, errors = verify_audit(their_audit, dict(in_session.turns.played))
    in_session.turns = ReferenceV3Inbox(window=_t("reorder_window", 4))  # reset for next sub-game
    distinct = len(set(rl_moves))
    outcome = "capture" if captured else "survival"
    ended_at = datetime.now(UTC).isoformat()
    print(
        f"[match] sg{sub_game} audit ok={ok} errors={errors[:2]} outcome={outcome} "
        f"rl_moves={len(rl_moves)} distinct={distinct} sample={rl_moves[:8]}"
    )
    gui_context.note_settled(sub_game, ok, outcome, role)
    # Collect the sealed history for the log/result artifacts.
    our_records = [
        {"commit": r.get("commit"), "nonce": r.get("nonce"), "payload": r.get("payload")}
        for r in out_session.local_records
    ]
    declared = {
        t.get("step"): {
            "barrier_placed": t.get("barrier_placed"),
            "capture_claim": t.get("capture_claim"),
            "hint": t.get("hint"),
        }
        for t in in_session.turn_messages
    }
    opp_records = [
        {
            "commit": rec.get("commit"),
            "declared": declared.get((rec.get("payload") or {}).get("step"), {}),
            "nonce": rec.get("nonce"),
            "payload": rec.get("payload"),
        }
        for rec in (their_audit.get("records") or [])
    ]
    if (
        captured
        and role == "police"
        and disputed_capture is None
        and settled_caught_cell is not None
    ):
        disputed_capture = _refine_disputed_trail(opp_records, settled_caught_cell, sub_game)
    # Mutual step-0 audit: their sealed step_zero must declare the same github_commit as
    # their negotiate identity (else they equivocated between handshake and audit).
    # Peers name the record differently — anrbj666 "step_zero", najamjad "system_spec"
    # (2026-08-13: their hardware/token declaration rode a system_spec record and our
    # summary recorded null). Accept either shape; the commit check below still only
    # fires when the record actually carries a github_commit.
    opp_sz = next(
        (
            r.get("payload")
            for r in opp_records
            if (r.get("payload") or {}).get("type") in ("step_zero", "system_spec")
        ),
        None,
    )
    sz_mismatch = None
    if opp_sz is not None:
        declared_commit = hs["opp_identity"].get("github_commit")
        sealed_commit = opp_sz.get("github_commit")
        if declared_commit and sealed_commit and declared_commit != sealed_commit:
            sz_mismatch = {"declared": declared_commit, "sealed": sealed_commit}
    summary = {
        "audit": "Verified OK" if ok else "FAILED",
        "outcome": outcome,
        "digest_match": None,
        "disputed_capture": disputed_capture,
        "turns_completed": len(rl_moves),
        "steps_sealed": len(our_records),
        "opponent_step_zero": opp_sz,
        "step_zero_mismatch": sz_mismatch,
        "started_at": hs["started_at"],
        "ended_at": ended_at,
        "role": role,
        "group_id": "vibecode",
        "opponent_group_id": opponent_group_hint,
    }
    row = {
        "sub_game": sub_game,
        "role": role,
        # Full wire experience of this window, both directions - feeds the
        # game-record artifact only (score_series copies fields, never rows).
        "wire_turns": {
            "sent": [dict(t) for t in getattr(out_session, "sent_turns", [])],
            "received": [dict(t) for t in in_session.turn_messages],
        },
        "audit_ok": ok,
        "outcome": outcome,
        "rl_move_count": len(rl_moves),
        "distinct_moves": distinct,
        "our_records": our_records,
        "opp_records": opp_records,
        "summary": summary,
        "started_at": hs["started_at"],
        "ended_at": ended_at,
        "our_commit": hs["our_commit"],
        "opp_identity": hs["opp_identity"],
        "opponent_group": hs["negotiated"].opponent_group,
    }
    settled_row.remember(in_session, row)  # survives a post-audit peer 502
    return row
