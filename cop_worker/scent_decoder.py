"""Recover the opponent's position from the CLAMPED wire scent field.

Why this exists
---------------
The negotiated wire law (``multiplicative_book_v1``, sha ``934c220d…``) accumulates

    g_t[c] = clamp(0.9 * g_{t-1}[c] + e(d2(c, p_t)), 0.0, 0.9)

where ``p_t`` is the emitter's cell and ``e`` is the radial book kernel. The 0.9 clamp
saturates ~40 of 49 cells by step ~10, so ``argmax g_t`` degenerates into a 40-way tie and
"follow the scent peak" stops being a defined instruction. A policy fed ``g_t`` directly is
blind on ~95% of steps.

But the clamp destroys information only where it *bites*. Everywhere else the residual

    r_t[c] = g_t[c] - 0.9 * g_{t-1}[c]

is exactly ``e(d2(c, p_t))``, and ``e`` is injective on the six kernel radii -- so each
unsaturated cell reports its exact squared distance to the emitter. Better still, the
``d2 == 8`` ring can never saturate (``0.9*0.9 + 0.04 = 0.85 < 0.9``), so clean signal
always survives. Inverting the law is therefore a consistency test, not an estimate:

    cell c is consistent with emitter p  <=>
        g_t[c] < 0.9  and  g_t[c] == 0.9*g_{t-1}[c] + e(d2(c,p))     (clamp inactive)
        g_t[c] == 0.9  and  0.9*g_{t-1}[c] + e(d2(c,p)) >= 0.9       (clamp active)

Intersecting that test over all 49 cells normally pins the emitter to a single cell.

This is an OBSERVATION-SIDE transform only. It reads the field the peer already sends and
changes nothing we transmit, so the negotiated scent contract is untouched and the peer
cannot observe that we do it.
"""

from __future__ import annotations

import numpy as np

# Kernel is keyed by squared Euclidean distance; mirrors RulesEngine._SCENT_KERNEL.
DECAY = 0.9
CLAMP_HI = 0.9


def _kernel() -> dict[int, float]:
    from cop_worker.rules_engine import RulesEngine

    return dict(RulesEngine._SCENT_KERNEL)


def _emission_table(grid_size: int) -> np.ndarray:
    """``table[p_idx, c_idx]`` = emission at cell ``c`` for an emitter at ``p``.

    Precomputed once per grid size: the decoder is called every step of every game, and the
    kernel lookup is the whole inner loop.
    """
    kernel = _kernel()
    n = grid_size
    cells = [(x, y) for y in range(n) for x in range(n)]
    table = np.zeros((n * n, n * n))
    for pi, (px, py) in enumerate(cells):
        for ci, (cx, cy) in enumerate(cells):
            table[pi, ci] = kernel.get((cx - px) ** 2 + (cy - py) ** 2, 0.0)
    return table


class EmitterDecoder:
    """Stateful inverse of the clamped wire scent law.

    Feed it the opponent-scent grid as received each step; it returns a posterior over the
    opponent's current cell. ``tol`` absorbs peer-side float noise -- the contract allows
    ``rounding_decimals: null`` or 4, and evaluation order is not pinned by IEEE-754, so
    exact equality would be brittle.
    """

    def __init__(self, grid_size: int, tol: float = 2e-3) -> None:
        self.n = grid_size
        self.tol = tol
        self._emission = _emission_table(grid_size)
        self._prev: np.ndarray | None = None

    def reset(self) -> None:
        self._prev = None

    def decode(self, field) -> np.ndarray:
        """Return an ``n x n`` posterior over the emitter's cell (sums to 1).

        Uniform over the cells consistent with the observation. Falls back to a uniform
        grid when the field is empty (step 1, nothing emitted yet) or when no candidate
        survives -- a peer whose arithmetic differs from ours must degrade to "no
        information", never to a confident wrong answer.
        """
        g = np.asarray(field, dtype=float).reshape(-1)
        n = self.n
        if g.size != n * n:
            return np.full((n, n), 1.0 / (n * n))

        prev = np.zeros_like(g) if self._prev is None else self._prev
        self._prev = g.copy()

        if not np.any(g > 0.0):
            return np.full((n, n), 1.0 / (n * n))

        decayed = DECAY * prev  # what the field would be with no fresh emission
        saturated = g >= CLAMP_HI - self.tol

        # predicted[p, c] = pre-clamp value at c if the emitter sat at p this step.
        predicted = decayed[None, :] + self._emission
        # Unsaturated cells must match exactly; saturated cells only need to reach the clamp.
        ok_unsat = np.abs(predicted - g[None, :]) <= self.tol
        ok_sat = predicted >= CLAMP_HI - self.tol
        consistent = np.where(saturated[None, :], ok_sat, ok_unsat).all(axis=1)

        if not consistent.any():
            return np.full((n, n), 1.0 / (n * n))
        post = consistent.astype(float)
        return (post / post.sum()).reshape(n, n)

    def decode_argmax(self, field) -> tuple[int, int] | None:
        """Best single guess as ``(x, y)``, or ``None`` if the posterior is uninformative."""
        post = self.decode(field)
        if float(post.max()) <= 1.0 / (self.n * self.n) + 1e-12:
            return None
        r, c = np.unravel_index(int(post.argmax()), post.shape)
        return (int(c), int(r))
