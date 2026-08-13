"""Simple legal movement + template hints. Fidelity over strength (bench opponent)."""

from __future__ import annotations

import random

#: Wire cells are [row, col]; deltas live in row/col space (N = row-1, E = col+1).
DELTAS = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1), "STAY": (0, 0)}

_COP_HINTS = [
    "I can smell you nearby, give up now.",
    "Closing in on your trail, thief.",
    "The net is tightening around this block.",
    "Every alley in this district is watched.",
]
_THIEF_HINTS = [
    "You will never find me in these streets.",
    "Still three blocks ahead of you, officer.",
    "The crowd hides me well tonight.",
    "Chasing shadows again, are we?",
]


def hint_for(role: str, step: int) -> str:
    """A short free-language hint every turn (template, within the 15-word cap)."""
    pool = _COP_HINTS if role == "police" else _THIEF_HINTS
    return pool[step % len(pool)]


def scent_argmax(smell_grid: dict | None, board: int) -> list[int] | None:
    """The strongest cell of an inbound wire field ``{"r,c": v}`` — the chase target."""
    best, best_value = None, 0.0
    for cell, value in (smell_grid or {}).items():
        try:
            row, col = (int(part) for part in str(cell).split(","))
        except ValueError:
            continue
        if 0 <= row < board and 0 <= col < board and float(value) > best_value:
            best, best_value = [row, col], float(value)
    return best


def legal_moves(pos: list[int], board: int, blocked: set | frozenset = frozenset()) -> list[str]:
    out = []
    for move, (dr, dc) in DELTAS.items():
        row, col = pos[0] + dr, pos[1] + dc
        if 0 <= row < board and 0 <= col < board and (row, col) not in blocked:
            out.append(move)
    return out


def cop_move(pos: list[int], target: list[int] | None, board: int) -> str:
    """Greedy chase: minimize Manhattan distance to the scent argmax (ties random)."""
    moves = legal_moves(pos, board)
    if target is None:
        return random.choice(moves)

    def dist(move: str) -> int:
        dr, dc = DELTAS[move]
        return abs(pos[0] + dr - target[0]) + abs(pos[1] + dc - target[1])

    best = min(dist(m) for m in moves)
    return random.choice([m for m in moves if dist(m) == best])


def thief_move(pos: list[int], board: int, blocked: set) -> str:
    """Random legal move: never off-board, never into a cop barrier."""
    moves = [m for m in legal_moves(pos, board, blocked) if m != "STAY"]
    return random.choice(moves) if moves else "STAY"


def apply_move(pos: list[int], move: str) -> list[int]:
    dr, dc = DELTAS[move]
    return [pos[0] + dr, pos[1] + dc]
