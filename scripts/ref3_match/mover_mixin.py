"""Board-state concerns shared by the move engine: scent I/O and barrier rules.

Mixed into :class:`ref3_match.mover.RLMover`. Requires the host to provide
``role``, ``grid``, ``pos``, ``barriers``, ``_chebyshev_trail``, ``_board``,
``_rules`` (the mover's __init__ sets them all).
"""

from __future__ import annotations

from ref3_match.gui_bridge import publish_view


class MoverStateMixin:
    def _opponent_scent_grid(self, smell_grid: dict) -> list[list[float]]:
        """Convert the peer's transmitted {'r,c': v} field to our NxN grid."""
        n = self.grid
        g = [[0.0] * n for _ in range(n)]
        for cell, val in (smell_grid or {}).items():
            try:
                r, c = (int(t) for t in cell.split(","))
            except (ValueError, AttributeError):
                continue
            if 0 <= r < n and 0 <= c < n:
                g[r][c] = float(val)
        # Optional live GUI (guarded no-op when none is registered; never affects play).
        publish_view(self, g)
        return g

    def observe_peer_barrier(self, cell) -> None:
        """Track a cop-placed barrier while WE are the thief.

        Training always fed the thief the true barrier list (``known_barriers`` +
        the legal-move mask in ``train_recurrent._observation``); serving fed ``[]``,
        so the net could neither route around walls nor know it was enclosed. As cop,
        ``self.barriers`` are OUR placements and the peer thief never places — ignore.
        """
        if self.role != "thief" or not isinstance(cell, (list, tuple)) or len(cell) != 2:
            return
        try:
            bx, by = int(cell[0]), int(cell[1])
        except (TypeError, ValueError):
            return
        if 0 <= bx < self.grid and 0 <= by < self.grid and [bx, by] not in self.barriers:
            self.barriers.append([bx, by])

    def self_capture_check(self) -> str | None:
        """Rule 46/47 self-check — the endings only the thief can see (must be SAID).

        Rule 46: a barrier on our cell is a capture. Rule 47: no orthogonal escape
        (every neighbour barrier or off-board) is a capture — STAY does not rescue.
        Returns "rule46"/"rule47" or None. Silence here forks the game: we'd claim a
        survival the cop's audit scores as capture — the rule-35 shape that zeroes
        BOTH teams (imreeyal §3.14, kit WARNINGS §5c).
        """
        if self.role != "thief":
            return None
        x, y = self.pos
        if [x, y] in self.barriers:
            return "rule46"
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.grid and 0 <= ny < self.grid and [nx, ny] not in self.barriers:
                return None
        return "rule47"

    def our_smell_grid(self) -> dict:
        """Byte-exact scent around our own position under the LOCKED model, wire {'r,c': v}."""
        if self._chebyshev_trail is not None:
            # Wire key is "row,col"; our pos is [x, y] → center (y, x).
            return self._chebyshev_trail.full_turn((self.pos[1], self.pos[0]))
        self._board.thief_position = list(self.pos)  # emitter = us
        self._rules.update_scent()
        field = self._rules.get_scent_field()
        n = self.grid
        return {f"{r},{c}": field[r][c] for r in range(n) for c in range(n) if field[r][c] > 0.0}
