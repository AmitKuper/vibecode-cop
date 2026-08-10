"""``subtractive_chebyshev_v1`` — the kit's reference scent model, byte-exact.

The league kit registers two scent laws; this is the reference's own (locked doc sha
``81ebee59…``): linear Chebyshev falloff, merge-by-max trail, subtractive decay, rounded
to 3 places, deposit-then-decay — so the freshly-emitted centre leaves the sender at
``intensity - decay`` (0.8 on default terms), which is what crosses the wire.

Arithmetic mirrors the kit's ``verify_vectors.ref_smell_emit`` / ``ref_smell_decay`` and
``sparring/rules/scent.py::Trail.full_turn`` exactly; the fixtures in
``tests/test_scent_chebyshev.py`` pin the bytes against the kit's ``vectors/pheromone.json``
values so the two implementations cannot drift silently.

Coordinates: wire form is ``{"r,c": value}`` with r=row (y), c=col (x) — the same
convention ``RLMover.our_smell_grid`` and ``_opponent_scent_grid`` already use.
"""

from __future__ import annotations

CHEBYSHEV_MODEL = "subtractive_chebyshev_v1"


def chebyshev_emit(
    center: tuple[int, int], intensity: float, grid_size: int, board_size: int
) -> dict[str, float]:
    """Radial emission around ``center=(row, col)`` — kit ``ref_smell_emit``.

    half = grid_size // 2; falloff = intensity / (half + 1);
    value = round(max(0, intensity - falloff * chebyshev(cell, center)), 3);
    board-clipped, zero cells omitted.
    """
    half = grid_size // 2
    falloff = intensity / (half + 1)
    out: dict[str, float] = {}
    for dr in range(-half, half + 1):
        for dc in range(-half, half + 1):
            r, c = center[0] + dr, center[1] + dc
            if 0 <= r < board_size and 0 <= c < board_size:
                value = round(max(0.0, intensity - falloff * max(abs(dr), abs(dc))), 3)
                if value > 0.0:
                    out[f"{r},{c}"] = value
    return out


def chebyshev_decay(field: dict[str, float], decay: float) -> dict[str, float]:
    """One game-step subtractive decay, clamped at 0, rounded to 3 — kit ``ref_smell_decay``."""
    return {k: round(max(0.0, v - decay), 3) for k, v in field.items()}


class ChebyshevTrail:
    """One agent's own trail in wire form — kit ``Trail`` (reference model branch).

    ``full_turn(center)``: emit (gated on ``emit_intensity >= min_center_intensity``),
    merge by max into the standing field, then decay everything and drop zeros. The
    returned snapshot is exactly what goes on the wire: peak ``intensity - decay``.
    """

    def __init__(
        self,
        board_size: int,
        *,
        field_size: int = 5,
        emit_intensity: float = 0.9,
        decay_per_step: float = 0.1,
        min_center_intensity: float = 0.5,
    ) -> None:
        self.board_size = board_size
        self.field_size = field_size
        self.emit_intensity = emit_intensity
        self.decay_per_step = decay_per_step
        self.min_center_intensity = min_center_intensity
        self.field: dict[str, float] = {}

    def full_turn(self, center: tuple[int, int]) -> dict[str, float]:
        """Advance one full turn for an emitter at ``center=(row, col)``; return the wire field."""
        if self.emit_intensity >= self.min_center_intensity:
            emitted = chebyshev_emit(center, self.emit_intensity, self.field_size, self.board_size)
            for key, value in emitted.items():
                if value > self.field.get(key, 0.0):
                    self.field[key] = value
        self.field = {
            k: v for k, v in chebyshev_decay(self.field, self.decay_per_step).items() if v > 0.0
        }
        return self.snapshot()

    def snapshot(self) -> dict[str, float]:
        """What crosses the wire: only cells that still carry something."""
        return dict(self.field)

    def as_grid(self) -> list[list[float]]:
        """Render the current field as an NxN row-major grid (absent cells = 0.0)."""
        return field_to_grid(self.field, self.board_size)

    def reset(self) -> None:
        self.field = {}


def field_to_grid(field: dict[str, float], board_size: int) -> list[list[float]]:
    """Convert a wire ``{"r,c": v}`` field to a board-size row-major grid."""
    grid = [[0.0] * board_size for _ in range(board_size)]
    for cell, value in (field or {}).items():
        try:
            r, c = (int(t) for t in cell.split(","))
        except (ValueError, AttributeError):
            continue
        if 0 <= r < board_size and 0 <= c < board_size:
            grid[r][c] = float(value)
    return grid


class ChebyshevFields:
    """Drop-in ``ScentFields`` counterpart for training under the chebyshev law.

    Same interface (``update`` / ``cop_observation_scent`` / ``thief_observation_scent``)
    but each agent's field is a :class:`ChebyshevTrail`, so the observation grids carry
    exactly the post-decay snapshots the reference-v3 wire transmits. Positions are
    ``(x, y)`` as in ``ScentFields.update``; trails store rows/cols internally.
    """

    def __init__(self, grid_size: int) -> None:
        self.grid_size = grid_size
        self._cop_trail = ChebyshevTrail(grid_size)
        self._thief_trail = ChebyshevTrail(grid_size)

    @classmethod
    def zeros(cls, grid_size: int) -> ChebyshevFields:
        return cls(grid_size)

    def update(self, cop_pos: tuple[int, int], thief_pos: tuple[int, int]) -> ChebyshevFields:
        """Advance both trails one full turn; mutates and returns self (snapshot cadence)."""
        self._cop_trail.full_turn((cop_pos[1], cop_pos[0]))
        self._thief_trail.full_turn((thief_pos[1], thief_pos[0]))
        return self

    def cop_observation_scent(self) -> list[list[float]]:
        """Cop sees the THIEF's transmitted field."""
        return self._thief_trail.as_grid()

    def thief_observation_scent(self) -> list[list[float]]:
        """Thief sees the COP's transmitted field."""
        return self._cop_trail.as_grid()
