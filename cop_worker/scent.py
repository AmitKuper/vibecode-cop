"""Symmetric scent model per Appendix F specification."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SCENT_CENTER_INTENSITY = 0.9
DECAY = 0.9
KERNEL_RADIUS = 2  # 5x5 kernel


def compute_scent_grid(
    cop_position: list[int],
    board_size: int,
    grid_size: int,
    emit_intensity: float,
    decay_per_step: float,
) -> list[list[float]]:
    """Compute the scent grid around cop_position.

    The grid spans grid_size × grid_size cells starting from the board-clamped
    top-left corner max(0, cx - half) × max(0, cy - half). Each cell's value
    is emit_intensity × (1 - decay_per_step)^(Manhattan distance from cop).
    Cells outside the board have scent 0.0.

    Args:
        cop_position: [x, y] position of the cop on the board.
        board_size: Size of the board (N×N).
        grid_size: Size of the scent grid (e.g. 5 → 5×5 grid).
        emit_intensity: Intensity at the cop cell.
        decay_per_step: Fraction of intensity lost per Manhattan step.

    Returns:
        grid_size × grid_size list of floats.
    """
    cx, cy = cop_position
    half = grid_size // 2
    start_x = max(0, cx - half)
    start_y = max(0, cy - half)
    grid = []
    for row_idx in range(grid_size):
        ny = start_y + row_idx
        row = []
        for col_idx in range(grid_size):
            nx = start_x + col_idx
            if 0 <= nx < board_size and 0 <= ny < board_size:
                dist = abs(nx - cx) + abs(ny - cy)
                value = emit_intensity * ((1.0 - decay_per_step) ** dist)
            else:
                value = 0.0
            row.append(round(value, 9))
        grid.append(row)
    return grid


def _radial_kernel(radius: int) -> np.ndarray:
    """Fixed Appendix-F 5x5 Euclidean radial kernel."""
    size = 2 * radius + 1
    kernel = np.zeros((size, size))
    center = radius
    for r in range(size):
        for c in range(size):
            dist_sq = (r - center) ** 2 + (c - center) ** 2
            kernel[r][c] = {
                0: 0.90,
                1: 0.62,
                2: 0.42,
                4: 0.20,
                5: 0.14,
                8: 0.04,
            }.get(dist_sq, 0.0)
    return kernel


@dataclass
class ScentFields:
    cop_scent: np.ndarray  # NxN, tracks cop presence
    thief_scent: np.ndarray  # NxN, tracks thief presence
    grid_size: int

    @classmethod
    def zeros(cls, grid_size: int) -> ScentFields:
        return cls(
            cop_scent=np.zeros((grid_size, grid_size)),
            thief_scent=np.zeros((grid_size, grid_size)),
            grid_size=grid_size,
        )

    def update(self, cop_pos: tuple[int, int], thief_pos: tuple[int, int]) -> ScentFields:
        """Decay then add kernel around each agent. Returns new ScentFields.

        Under ``COPTHIEF_WIRE_SCENT=1`` accumulation switches to the wire law
        ``clamp(0.9*old + kernel, 0, 0.9)`` (``RulesEngine.update_scent``, no rounding) so
        training matches the wire; default keeps the historical unclamped law (~6.5 peak).
        """
        from cop_worker.rl.obs_mode import wire_scent_enabled

        kernel = _radial_kernel(KERNEL_RADIUS)
        radius = KERNEL_RADIUS
        clamped = wire_scent_enabled()

        new_cop = self.cop_scent * DECAY
        new_thief = self.thief_scent * DECAY

        for field, pos in [(new_cop, cop_pos), (new_thief, thief_pos)]:
            x0, y0 = pos
            r0, c0 = y0, x0
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    r, c = r0 + dr, c0 + dc
                    kr, kc = dr + radius, dc + radius
                    if (
                        0 <= r < self.grid_size
                        and 0 <= c < self.grid_size
                        and 0 <= kr < len(kernel)
                        and 0 <= kc < len(kernel[0])
                    ):
                        if clamped:
                            field[r][c] = min(0.9, max(0.0, field[r][c] + kernel[kr][kc]))
                        else:
                            field[r][c] = round(field[r][c] + kernel[kr][kc], 4)

        return ScentFields(cop_scent=new_cop, thief_scent=new_thief, grid_size=self.grid_size)

    def cop_observation_scent(self) -> list[list[float]]:
        """Cop sees THIEF scent only."""
        return self.thief_scent.tolist()

    def thief_observation_scent(self) -> list[list[float]]:
        """Thief sees COP scent only."""
        return self.cop_scent.tolist()


def make_scent_fields(grid_size: int):
    """Field factory dispatching on the configured scent law (``COPTHIEF_SCENT_MODEL``).

    Training and evaluation construct their fields through this seam so that switching the
    Step-0 scent model switches the physics the nets are trained on in ONE place. Both
    returned types share the ``update`` / ``cop_observation_scent`` /
    ``thief_observation_scent`` interface.
    """
    from cop_worker.rl.obs_mode import chebyshev_scent_enabled

    if chebyshev_scent_enabled():
        from cop_worker.scent_chebyshev import ChebyshevFields

        return ChebyshevFields.zeros(grid_size)
    return ScentFields.zeros(grid_size)
