"""Persist finished human-vs-model games as replayable game records.

Finished games are written in the SAME ``game_record_v1`` schema the replay
viewer already renders (positions in wire [row,col], sparse "row,col" scent,
``barrier_placed`` per step), so a human game gets the full replay — board,
walls, role/group header — with zero new viewer code. "ours" is the MODEL,
"theirs" is the HUMAN; groups ["human", "vibecode"].
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "results"


def note(g: dict, actor: str, role: str, action: str, barrier: list | None = None) -> None:
    """Append one half-move to the game's history (positions AFTER the move)."""
    g.setdefault("history", []).append(
        {
            "step": g["step"],
            "actor": actor,  # "human" | "model"
            "role": role,  # "cop" | "thief"
            "action": action,
            "cop": list(g["cop"]),
            "thief": list(g["thief"]),
            "barrier": list(barrier) if barrier else None,
            "scent": dict(g.get(f"scent_{role}") or {}),
        }
    )


def _wire(pos: list) -> list:
    return [int(pos[1]), int(pos[0])]  # internal [x,y] -> wire [row,col]


def persist_if_over(g: dict) -> None:
    """Write the record once, when the game has ended."""
    if not g.get("over") or g.get("_persisted") or not g.get("history"):
        return
    g["_persisted"] = True
    model_role = "thief" if g["human_role"] == "cop" else "cop"
    rows: dict[int, dict] = {}
    for ev in g["history"]:
        side = "ours" if ev["actor"] == "model" else "theirs"
        own = ev["cop"] if ev["role"] == "cop" else ev["thief"]
        rows.setdefault(ev["step"], {})[side] = {
            "position": _wire(own),
            "move": ev["action"],
            "smell_grid": ev["scent"],
            "barrier_placed": _wire(ev["barrier"]) if ev["barrier"] else None,
        }
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    doc = {
        "_schema": "game_record_v1",
        "game_id": "human-vs-model",
        "our_role": "police" if model_role == "cop" else "thief",
        "groups": ["human", "vibecode"],
        "sub_game_number": 0,
        "human_role": g["human_role"],
        "outcome": g.get("outcome"),
        "started_at": stamp,
        "steps": [{"step": s, **rows[s]} for s in sorted(rows)],
    }
    import json

    out = RESULTS / f"record_human-vs-model_{stamp}_{g['id'][:6]}.json"
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    g["record_file"] = out.name
