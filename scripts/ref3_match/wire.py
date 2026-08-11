"""Wire-boundary cell conversion and caught=true corroboration (SPEC §3.1)."""

from __future__ import annotations


def _to_wire_cell(cell) -> list[int] | None:
    """Our internal [x, y] -> the kit's wire [row, col].

    The kit's convention is authoritative: its turnloop feeds ``engine.position``
    straight into ``ref_smell_emit``, whose keys are ``"row,col"`` — so every
    cell-valued wire field (position, barrier_placed, capture_claim,
    claim_response.claim) is [row, col]. We found this live (2026-08-10 rehearsal):
    our [x, y] barrier registered TRANSPOSED in the peer's physics, its thief
    legally dodged "through" our wall, and off-diagonal captures could never
    settle. Internal state stays [x, y]; conversion happens only at the boundary.
    """
    if not isinstance(cell, (list, tuple)) or len(cell) != 2:
        return None
    return [int(cell[1]), int(cell[0])]


def _from_wire_cell(cell) -> list[int] | None:
    """The kit's wire [row, col] -> our internal [x, y]."""
    return _to_wire_cell(cell)  # transposition is its own inverse


def _corroborate_caught(cell, our_claim, our_barriers, our_pos, grid) -> tuple[str, bool]:
    """Classify and live-corroborate a thief ``caught=true`` (SPEC §3.1).

    ANSWER: the cell echoes our last capture_claim → co-location, corroborated by
    construction (we claimed our own cell). CONCESSION: any other cell — corroborated
    only under OUR OWN barrier record (a barrier of ours on that cell, rule 46, or every
    orthogonal neighbour ours/off-board, rule 47), never under the thief's reported
    list. The trail-end refinement happens at audit time, once records are revealed.
    """
    if not isinstance(cell, (list, tuple)) or len(cell) != 2:
        return "malformed", False
    cell = [int(cell[0]), int(cell[1])]
    if our_claim is not None and cell == list(our_claim):
        return "answer", True
    ours = [list(b) for b in our_barriers]
    if cell in ours:
        return "concession", True
    for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0)):
        nx, ny = cell[0] + dx, cell[1] + dy
        if 0 <= nx < grid and 0 <= ny < grid and [nx, ny] not in ours:
            return "concession", False
    return "concession", True
