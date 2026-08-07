"""SyntheticBeliefProvider — full board×board belief maps for RL training and tests."""

from __future__ import annotations

import numpy as np


class SyntheticBeliefProvider:
    """Produces board×board probability maps identical in shape to production BeliefEngine.

    Used for RL training and automated tests. Never calls an LLM.
    Swapping this for BeliefEngine requires zero changes to RL code.
    """

    def get_belief_map(
        self,
        board_size: int,
        true_opponent_position: tuple[int, int],
        confidence_level: str = "high",
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """Return a (board_size, board_size) probability map summing to 1.0.

        Args:
            board_size: Size of the square board.
            true_opponent_position: (row, col) of the true opponent location.
            confidence_level: 'high' (80% mass at true pos), 'medium' (50% in 3x3),
                              or 'low' (near-uniform).
            rng: Optional numpy random generator for reproducibility.

        Returns:
            np.ndarray of shape (board_size, board_size), dtype float32, summing to 1.0.
        """
        if rng is None:
            rng = np.random.default_rng()

        belief = np.zeros((board_size, board_size), dtype=np.float32)
        r, c = true_opponent_position

        if confidence_level == "high":
            belief[r, c] = 0.8
            remaining = 0.2
            neighbors = self._neighbors(r, c, board_size)
            if neighbors:
                per_neighbor = remaining / len(neighbors)
                for nr, nc in neighbors:
                    belief[nr, nc] = per_neighbor
            else:
                belief[r, c] = 1.0

        elif confidence_level == "medium":
            region = self._region3x3(r, c, board_size)
            per_cell = 0.5 / len(region)
            for rr, cc in region:
                belief[rr, cc] = per_cell
            flat = belief.flatten()
            flat += rng.dirichlet(np.ones(len(flat))) * 0.5
            belief = flat.reshape(board_size, board_size).astype(np.float32)

        else:  # low — near-uniform
            noise = rng.dirichlet(np.ones(board_size * board_size))
            belief = noise.reshape(board_size, board_size).astype(np.float32)

        total = belief.sum()
        if total > 0:
            belief /= total
        return belief

    def _neighbors(self, r: int, c: int, size: int) -> list[tuple[int, int]]:
        """Return valid orthogonal neighbors of (r, c) within (size x size) board."""
        candidates = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
        return [(rr, cc) for rr, cc in candidates if 0 <= rr < size and 0 <= cc < size]

    def _region3x3(self, r: int, c: int, size: int) -> list[tuple[int, int]]:
        """Return all valid cells in 3x3 region centred at (r, c)."""
        cells = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < size and 0 <= cc < size:
                    cells.append((rr, cc))
        return cells
