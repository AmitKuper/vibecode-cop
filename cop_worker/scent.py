"""Symmetric scent model per Appendix F specification."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SCENT_CENTER_INTENSITY = 0.9
DECAY = 0.9
KERNEL_RADIUS = 2  # 5x5 kernel


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
        """Decay then add kernel around each agent. Returns new ScentFields."""
        kernel = _radial_kernel(KERNEL_RADIUS)
        radius = KERNEL_RADIUS

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
                        field[r][c] = round(field[r][c] + kernel[kr][kc], 4)

        return ScentFields(cop_scent=new_cop, thief_scent=new_thief, grid_size=self.grid_size)

    def cop_observation_scent(self) -> list[list[float]]:
        """Cop sees THIEF scent only."""
        return self.thief_scent.tolist()

    def thief_observation_scent(self) -> list[list[float]]:
        """Thief sees COP scent only."""
        return self.cop_scent.tolist()
