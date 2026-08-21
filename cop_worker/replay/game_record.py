"""Replay adapter for game-record artifacts (record_<game>_gNN.json).

A game record is OBSERVATIONAL: it stores what each side actually transmitted
per step (scent bytes, hints, claims) plus positions - ours sealed live, the
opponent's filled from the audit reveal. It is not commit-reveal evidence, so
the viewer labels it RECORDED rather than Verified OK / TAMPERED; integrity
still comes from the sealed log_*.json of the same window.
"""

from __future__ import annotations

RECORDED = "RECORDED (observational; integrity via the sealed log)"


def is_game_record(doc: dict) -> bool:
    return isinstance(doc, dict) and doc.get("_schema") == "game_record_v1"


def _grid(smell: dict | None) -> dict:
    return {k: float(v) for k, v in (smell or {}).items() if isinstance(k, str)}


def record_timeline(doc: dict, board_size: int = 7) -> tuple[str, list[dict]]:
    """(overall_label, steps) shaped like the /api/replay/steps entries.

    Chronological, thief before cop within a step (thief moves first). Boards
    carry the RECORDED scent bytes - no reconstruction involved.
    """
    our_role = "police" if doc.get("our_role") == "police" else "thief"
    role_of = {"ours": our_role, "opponent": "thief" if our_role == "police" else "police"}
    latest_pos: dict = {"police": None, "thief": None}
    latest_scent: dict = {"police": {}, "thief": {}}
    walls: list = []
    entries = []
    for row in doc.get("steps") or []:
        step = row.get("step")
        sides = [("ours", row.get("ours") or {}), ("opponent", row.get("theirs") or {})]
        sides.sort(key=lambda sv: 0 if role_of[sv[0]] == "thief" else 1)
        for side, view in sides:
            role = role_of[side]
            pos = view.get("position")
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                # wire positions are [row,col]; the viewer draws markers as (x,y)
                latest_pos[role] = [int(pos[1]), int(pos[0])]
            if view.get("smell_grid"):
                latest_scent[role] = _grid(view["smell_grid"])
            placed = view.get("barrier_placed")
            if isinstance(placed, (list, tuple)) and len(placed) == 2:
                cell = [int(placed[0]), int(placed[1])]
                if cell not in walls:
                    walls.append(cell)
            commit = str(view.get("commit") or "")
            entries.append(
                {
                    "index": len(entries),
                    "side": side,
                    "step": step,
                    "role": role,
                    "ok": True,
                    "payload": {
                        "move": view.get("move"),
                        "position": view.get("position"),
                        "intent": view.get("intent"),
                        "hint": view.get("hint"),
                        "barrier_placed": view.get("barrier_placed"),
                    },
                    "stored_commit": commit,
                    "recomputed_commit": commit,
                    "board": {
                        "cop": list(latest_pos["police"]) if latest_pos["police"] else None,
                        "thief": list(latest_pos["thief"]) if latest_pos["thief"] else None,
                        "barriers": [list(w) for w in walls],
                        "scent_cop": dict(latest_scent["police"]),
                        "scent_thief": dict(latest_scent["thief"]),
                        "scent_source": "recorded",
                    },
                }
            )
    return RECORDED, entries
