"""Opponent position fix for the sighted search stack, with last-fix coasting.

Two position oracles, one resolver:

- ``subtractive_chebyshev_v1`` frames carry a unique fresh peak — the argmax IS
  the opponent's cell (`chebyshev_tracker`).
- ``multiplicative_book_v1`` frames saturate into a 0.9 plateau by ~step 10, but
  the law is exactly invertible (`cop_worker.scent_decoder`): when the inverse
  pins a UNIQUE consistent cell, that cell is the fix. Decoding reads only the
  field the peer already transmits — the negotiated scent contract is untouched.

Anything ambiguous coasts on the last confirmed fix; the resolver never returns
a confident guess. ``decode_book`` defaults to False so every existing chebyshev
pairing resolves byte-identically to the pre-decoder behavior.
"""

from __future__ import annotations

from cop_worker.rl.chebyshev_tracker import exact_opponent_cell


class OpponentFix:
    """Per-sub-game stateful resolver: scent frame -> opponent cell or None."""

    def __init__(self, decode_book: bool = False) -> None:
        self.decode_book = decode_book
        self._decoder = None
        self._last_seen: tuple[int, int] | None = None

    def reset(self) -> None:
        self._last_seen = None
        if self._decoder is not None:
            self._decoder.reset()

    def _decoded_cell(self, scent_grid, grid_size: int) -> tuple[int, int] | None:
        """The book-law inverse, accepted only when it pins a single cell."""
        import numpy as np

        from cop_worker.scent_decoder import EmitterDecoder

        if self._decoder is None:
            self._decoder = EmitterDecoder(grid_size)
        posterior = self._decoder.decode(scent_grid)
        if float(posterior.max()) < 0.999:  # ambiguous or uninformative
            return None
        row, col = np.unravel_index(int(posterior.argmax()), posterior.shape)
        return (int(col), int(row))

    def fix(self, scent_grid, grid_size: int) -> tuple[int, int] | None:
        """Resolve the opponent's current cell; coast on the last fix if unproven."""
        cell = None
        # The decoder differences consecutive frames, so when enabled it must see
        # EVERY frame — it runs first, before the chebyshev fallback.
        if self.decode_book and scent_grid:
            cell = self._decoded_cell(scent_grid, grid_size)
        if cell is None:
            cell = exact_opponent_cell(scent_grid, grid_size)
        if cell is None:
            return self._last_seen
        self._last_seen = cell
        return cell
