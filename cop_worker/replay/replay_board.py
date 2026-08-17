"""Board states for the replay timeline: positions + reconstructed scent.

The sealed payloads carry positions but not smell grids, so the replay
RECONSTRUCTS each side's transmitted field by replaying the revealed position
sequence through the same locked emitter the live game used
(``subtractive_chebyshev_v1`` via :class:`ChebyshevTrail` — byte-exact wire
law). Nothing here is hidden knowledge: every position was revealed at audit
time, and the field is a deterministic function of those positions.

Dialects that seal no position (anrbj666, rstabcde, uoh-sqak) still seal the
actual move each step, and start cells are protocol-fixed (police corner
(0,0), thief center (3,3) — book Appendix F). Their path is therefore
DEAD-RECKONED from the sealed moves, wall-clamped; validated exact against
the dialects that also serialize their state (288/288 positions match).
Boards carry the reconstruction in ``reckoned`` so viewers can label it.
"""

from __future__ import annotations

from cop_worker.replay.ref3_steps import record_role
from cop_worker.scent_chebyshev import ChebyshevTrail

#: Compass deltas in wire [x, y] — the label semantics every dialect shares.
_MOVES = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "STAY": (0, 0)}
#: Protocol start cells (book Appendix F defaults).
_START = {"police": (0, 0), "thief": (3, 3)}


def _position(payload: dict) -> tuple[int, int] | None:
    pos = payload.get("position")
    if isinstance(pos, list) and len(pos) == 2:
        return int(pos[0]), int(pos[1])  # wire [x, y]
    return None


def _move_label(payload: dict) -> str | None:
    """Sealed move as a compass label, across dialects (S / MOVE:S / action.move).

    Placement and hold labels (PLACE_E, BARRIER:E, barrier:3,4, HOLD:-) mean
    the mover stayed in place this step.
    """
    m = payload.get("move") or (payload.get("action") or {}).get("move")
    if not isinstance(m, str):
        return None
    m = m.upper().removeprefix("MOVE:")
    if m.startswith(("HOLD", "PLACE", "BARRIER")):
        return "STAY"
    return m if m in _MOVES else None


def board_states(steps: list, our_role: str = "police", board_size: int = 7) -> list[dict]:
    """One board per timeline entry: latest cop/thief positions + scent fields.

    ``steps`` is ref3_steps output in any order (the emitter replay sorts
    chronologically itself); ``our_role`` is the log's own role (summary.role).
    Role per record comes from :func:`record_role`. A record with no sealed
    position but a sealed move is dead-reckoned (see module docstring).
    """

    def _role(s) -> str:
        return record_role(s, our_role)

    ordered = sorted(
        (
            s
            for s in steps
            if s.step >= 1 and (_position(s.payload) or _move_label(s.payload))
        ),
        key=lambda s: (s.step, 0 if _role(s) == "thief" else 1),
    )
    # Replay each role's trail through the locked emitter, keyed by protocol step.
    trails = {"police": ChebyshevTrail(board_size), "thief": ChebyshevTrail(board_size)}
    latest: dict = {"police": None, "thief": None}
    reckoned: set[str] = set()
    by_step: dict[int, dict] = {}
    for rec in ordered:
        role = _role(rec)
        pos = _position(rec.payload)
        if pos is None:  # dead-reckon: sealed move from the last known cell
            x, y = latest[role] or _START[role]
            dx, dy = _MOVES[_move_label(rec.payload)]
            pos = (x + dx, y + dy)
            if not (0 <= pos[0] < board_size and 0 <= pos[1] < board_size):
                pos = (x, y)  # wall-clamped: an out-of-grid move is a stay
            reckoned.add("cop" if role == "police" else "thief")
        x, y = pos
        field = trails[role].full_turn((y, x))  # wire key "row,col"; center (row, col)
        latest[role] = [x, y]
        by_step[rec.step] = {
            "cop": list(latest["police"]) if latest["police"] else None,
            "thief": list(latest["thief"]) if latest["thief"] else None,
            "scent_cop": dict(field)
            if role == "police"
            else by_step.get(rec.step, {}).get("scent_cop", _snapshot(trails["police"])),
            "scent_thief": dict(field)
            if role == "thief"
            else by_step.get(rec.step, {}).get("scent_thief", _snapshot(trails["thief"])),
        }
    for entry in by_step.values():
        entry["reckoned"] = sorted(reckoned)
    # Map every timeline entry to the board at its protocol step (or the nearest before).
    out, current = [], {"cop": None, "thief": None, "scent_cop": {}, "scent_thief": {}, "reckoned": []}
    known = sorted(by_step)
    for s in steps:
        usable = [k for k in known if k <= s.step]
        current = by_step[usable[-1]] if usable else current
        out.append(current)
    return out


def _snapshot(trail: ChebyshevTrail) -> dict:
    try:
        return dict(trail.snapshot())
    except Exception:
        return {}
