"""Gamelet observation construction: scent grids, belief advance, local obs (mixin)."""

from __future__ import annotations

import logging

from cop_worker.gamelet_constants import _MOVE_DELTAS, _POLICY_TO_GAMELET_COP
from cop_worker.observation import BeliefState, LocalObservation

logger = logging.getLogger(__name__)


class GameletObservationMixin:
    """Scent/observation views the movement policy consumes."""

    def _opponent_scent_grid(self) -> list[list[float]]:
        """Convert the peer's transmitted smell {'r,c': v} into our NxN grid.

        Mirrors RLMover._opponent_scent_grid so the worker path observes the exact
        same opponent scent field the reference-v3 driver does.
        """
        n = self._grid_size
        g = [[0.0] * n for _ in range(n)]
        for cell, val in (self._opponent_smell or {}).items():
            try:
                r, c = (int(t) for t in cell.split(","))
            except (ValueError, AttributeError):
                continue
            if 0 <= r < n and 0 <= c < n:
                g[r][c] = float(val)
        return g

    def _own_smell_grid(self) -> dict[str, float]:
        """Emit OUR byte-exact book scent field around our current position as {'r,c': v}.

        Accumulates via RulesEngine.update_scent (the multiplicative_book_v1 law); call
        exactly once per step, after advancing our position. Sent on the wire so the
        opponent can smell us.
        """
        self._smell_board.thief_position = [self._own_position[0], self._own_position[1]]
        self._smell_rules.update_scent()
        field = self._smell_rules.get_scent_field()
        n = self._grid_size
        return {f"{r},{c}": field[r][c] for r in range(n) for c in range(n) if field[r][c] > 0.0}

    def _advance_own(self, action: dict, step: int) -> None:
        """Advance our tracked position by applying our own committed action.

        Movement clamps to board bounds (matching the domain / RLMover.apply). A barrier
        placement forfeits the move and, if quota remains and the target is in-bounds and
        free, records the barrier cell and decrements the remaining quota.

        Idempotent per step: a peer that re-sends a commit for an already-advanced step
        (retry / reorder) must not move us twice or double-spend barrier quota.
        """
        if step <= self._advanced_through_step:
            return
        self._advanced_through_step = step
        direction = str(action.get("direction", "stay"))
        x, y = self._own_position
        n = self._grid_size
        if direction.startswith("barrier_"):
            if self._own_barriers_remaining > 0:
                dx, dy = _MOVE_DELTAS.get(direction.split("_", 1)[1], (0, 0))
                bx, by = x + dx, y + dy
                if 0 <= bx < n and 0 <= by < n and [bx, by] not in self._known_barriers:
                    self._known_barriers.append([bx, by])
                    self._own_barriers_remaining -= 1
            return  # placement (legal or not) forfeits the move
        dx, dy = _MOVE_DELTAS.get(direction, (0, 0))
        nx, ny = x + dx, y + dy
        if 0 <= nx < n and 0 <= ny < n:
            self._own_position = (nx, ny)

    def _build_obs(self) -> tuple[LocalObservation, BeliefState]:
        """Build a LocalObservation and BeliefState for policy inference.

        Returns:
            Tuple of (LocalObservation, BeliefState) using current tracked state:
            our real position, the opponent scent received on the wire, and any
            known barriers.
        """
        n = self._grid_size
        obs = LocalObservation(
            own_position=self._own_position,
            own_barriers_remaining=self._own_barriers_remaining,
            known_barriers=[tuple(b) for b in self._known_barriers],
            opponent_scent=self._opponent_scent_grid(),
            last_hint=self._last_hint,
            step=self._step,
            gamelet=self.sub_game_number,
            grid_size=n,
        )
        belief = BeliefState.uniform(n, step=self._step)
        return obs, belief

    def _action_to_dict(self, action_name: str) -> dict:
        """Convert policy uppercase action name to gamelet action dict.

        Args:
            action_name: Uppercase action string from policy (e.g. "STAY", "PLACE_N").

        Returns:
            Action dict with 'type' and 'direction' keys.
        """
        direction = _POLICY_TO_GAMELET_COP.get(action_name, action_name)
        return {"type": "move", "direction": direction}
