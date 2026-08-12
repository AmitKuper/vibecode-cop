"""The two non-trainer scent laws the audit can feed the policies."""

from __future__ import annotations

import numpy as np


class ClampedScent:
    """The WIRE scent law: clamp(0.9*old + kernel, 0, 0.9) -- RulesEngine.update_scent.

    ``ScentFields`` (used by every trainer) omits the clamp, so its field grows to ~6-9 with
    a smooth peak at the emitter. The reference-v3 wire carries the clamped field, which
    saturates to a flat 0.9 plateau and loses the peak. Both laws share the same kernel, so
    this class isolates exactly one variable: the clamp.
    """

    def __init__(self, grid_size: int) -> None:
        self.n = grid_size
        self.cop = np.zeros((grid_size, grid_size))
        self.thief = np.zeros((grid_size, grid_size))

    def update(self, cop_pos, thief_pos) -> None:
        from cop_worker.rules_engine import RulesEngine

        kernel = RulesEngine._SCENT_KERNEL
        for field, (px, py) in ((self.cop, cop_pos), (self.thief, thief_pos)):
            for y in range(self.n):
                for x in range(self.n):
                    emission = kernel.get((x - px) ** 2 + (y - py) ** 2, 0.0)
                    field[y][x] = min(0.9, max(0.0, 0.9 * field[y][x] + emission))

    def observation_for(self, role: str) -> list[list[float]]:
        """Cop observes thief scent; thief observes cop scent."""
        return (self.thief if role == "cop" else self.cop).tolist()


class ChebyshevScent:
    """``subtractive_chebyshev_v1`` -- the OTHER registered model, which a peer may propose.

    Not our trained-on law. Ported from the kit's own reference so a measurement against it is
    trustworthy: ``sparring/rules/scent.py::Trail.full_turn`` emits, **merges by max** (not by
    addition -- this is the detail that keeps the field bounded), then decays subtractively,
    rounding to 3 places and dropping cells that reach zero.

    Emission (``vectors/pheromone.json``): ``half = field_size // 2``,
    ``falloff = intensity / (half + 1)``, and for every in-board cell within the ``field_size``
    window ``round(max(0, intensity - falloff * chebyshev), 3)`` -- so the rings are exactly
    {0.9, 0.6, 0.3} rather than the book kernel's six Euclidean steps.

    The consequence that matters for strength: with merge-by-max there is no accumulation above
    the emitted centre, so after one decay the field's peak is ``0.8``, never ``0.9``, and the
    argmax sits on the emitter instead of on a saturated plateau.
    """

    def __init__(
        self,
        grid_size: int,
        field_size: int = 5,
        emit_intensity: float = 0.9,
        decay_per_step: float = 0.1,
        min_center_intensity: float = 0.5,
    ) -> None:
        self.n = grid_size
        self.half = field_size // 2
        self.intensity = emit_intensity
        self.falloff = emit_intensity / (self.half + 1)
        self.decay_per_step = decay_per_step
        self.min_center = min_center_intensity
        self.cop: dict[tuple[int, int], float] = {}
        self.thief: dict[tuple[int, int], float] = {}

    def emit(self, pos) -> dict[tuple[int, int], float]:
        """The field one agent lays down this turn, keyed ``(row, col)`` == ``(y, x)``."""
        px, py = pos
        out: dict[tuple[int, int], float] = {}
        for r in range(py - self.half, py + self.half + 1):
            for c in range(px - self.half, px + self.half + 1):
                if not (0 <= r < self.n and 0 <= c < self.n):
                    continue
                cheb = max(abs(r - py), abs(c - px))
                value = round(max(0.0, self.intensity - self.falloff * cheb), 3)
                if value > 0.0:
                    out[(r, c)] = value
        return out

    def update(self, cop_pos, thief_pos) -> None:
        for field, pos in ((self.cop, cop_pos), (self.thief, thief_pos)):
            if self.intensity >= self.min_center:
                for key, value in self.emit(pos).items():
                    if value > field.get(key, 0.0):  # merge by MAX, not +=
                        field[key] = value
            for key in list(field):
                decayed = round(max(0.0, field[key] - self.decay_per_step), 3)
                if decayed > 0.0:
                    field[key] = decayed
                else:
                    del field[key]

    def observation_for(self, role: str) -> list[list[float]]:
        """Cop observes thief scent; thief observes cop scent. Absent cell == 0.0."""
        field = self.thief if role == "cop" else self.cop
        grid = [[0.0] * self.n for _ in range(self.n)]
        for (r, c), value in field.items():
            grid[r][c] = value
        return grid
