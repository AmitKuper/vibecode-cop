"""Pre-decay scent trail: najamjad's convention — the wire carries the field BEFORE decay."""

from __future__ import annotations

from cop_worker.scent_chebyshev import chebyshev_decay, chebyshev_emit


class PreDecayTrail:
    """Chebyshev trail whose wire snapshot is taken pre-decay (0.9 centre peak).

    Same arithmetic as :class:`cop_worker.scent_chebyshev.ChebyshevTrail`, but the
    emit-merge snapshot crosses the wire BEFORE the subtractive decay is applied —
    the convention najamjad transmits (peak ``emit_intensity``, not ``- decay``).
    """

    def __init__(self, board_size: int, terms: dict) -> None:
        self.board_size = board_size
        self.grid_size = int(terms.get("smell_grid_size", 5))
        self.intensity = float(terms.get("emit_intensity", 0.9))
        self.decay = float(terms.get("decay_per_step", 0.1))
        self.min_center = float(terms.get("min_center_intensity", 0.5))
        self.field: dict[str, float] = {}

    def full_turn(self, center: tuple[int, int]) -> dict[str, float]:
        """Emit at ``center=(row, col)``, snapshot pre-decay, then decay the field."""
        if self.intensity >= self.min_center:
            emitted = chebyshev_emit(center, self.intensity, self.grid_size, self.board_size)
            for key, value in emitted.items():
                if value > self.field.get(key, 0.0):
                    self.field[key] = value
        wire = dict(self.field)
        self.field = {k: v for k, v in chebyshev_decay(self.field, self.decay).items() if v > 0.0}
        return wire
