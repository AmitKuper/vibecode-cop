"""Audit-time refinement of settled captures (split from subgame_settle)."""

from __future__ import annotations


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
