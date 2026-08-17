"""The game-record artifact: every step of a window, both sides, as EXPERIENCED.

The sealed log proves integrity but drops the wire experience: the scent bytes
each side actually transmitted, the hints, the claims. This artifact keeps all
of it, merged per protocol step:

- ``ours``   = our sealed payload (position/move/intent) + the wire turn we sent
  (smell_grid, hint, barrier_placed, claim_response, win_claim).
- ``theirs`` = the wire turn we received (same fields, the ACTUAL bytes - not a
  reconstruction) + their revealed payload from the audit (position/move/intent,
  marked ``position_source: audit_reveal`` because it was hidden during play).

Written per played window to ``results/record_<game_id>_gNN.json``; the replay
viewer renders these directly (recorded scent instead of reconstructed).
"""

from __future__ import annotations

_WIRE_KEYS = (
    "hint",
    "smell_grid",
    "barrier_placed",
    "capture_claim",
    "claim_response",
    "win_claim",
    "commit",
)


def _by_step(turns: list[dict]) -> dict[int, dict]:
    """Latest wire turn per step (retries re-send identical bytes; last wins)."""
    out: dict[int, dict] = {}
    for t in turns or []:
        step = t.get("step")
        if isinstance(step, int) and step >= 1:
            out[step] = {k: t.get(k) for k in _WIRE_KEYS if t.get(k) is not None}
    return out


def _sealed_by_step(records: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in records or []:
        p = r.get("payload") or {}
        if isinstance(p.get("step"), int) and p["step"] >= 1:
            out[p["step"]] = p
    return out


def build_game_record(
    game_id: str,
    game_uid: str,
    sub_game: int,
    our_role: str,
    opponent: str,
    row: dict,
) -> dict:
    """Merge one settled sub-game row into the per-step both-sides record."""
    wire = row.get("wire_turns") or {}
    sent = _by_step(wire.get("sent"))
    received = _by_step(wire.get("received"))
    ours_sealed = _sealed_by_step(row.get("our_records") or [])
    theirs_sealed = _sealed_by_step(row.get("opp_records") or [])
    steps = []
    for step in sorted(set(sent) | set(received) | set(ours_sealed) | set(theirs_sealed)):
        ours = dict(sent.get(step, {}))
        for k in ("position", "move", "intent"):
            if k in ours_sealed.get(step, {}):
                ours[k] = ours_sealed[step][k]
        theirs = dict(received.get(step, {}))
        revealed = theirs_sealed.get(step, {})
        for k in ("position", "move", "intent"):
            if k in revealed:
                theirs[k] = revealed[k]
        if "position" in theirs:
            theirs["position_source"] = "audit_reveal"
        steps.append({"step": step, "ours": ours, "theirs": theirs})
    summary = row.get("summary") or {}
    return {
        "_schema": "game_record_v1",
        "report_type": "game_record",
        "game_id": game_id,
        "game_uid": game_uid,
        "sub_game_number": sub_game,
        "our_role": our_role,
        "groups": ["vibecode", opponent],
        "steps": steps,
        "summary": {
            "outcome": summary.get("outcome"),
            "audit": summary.get("audit"),
            "started_at": summary.get("started_at"),
            "ended_at": summary.get("ended_at"),
        },
        "note": (
            "observational record for replay - integrity evidence lives in the "
            "sealed log_*.json (commit-reveal), not here"
        ),
    }
