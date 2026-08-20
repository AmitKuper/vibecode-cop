"""The sighted search+hook teacher: production cop stack on exact state."""

from __future__ import annotations

from cop_worker.rl.pursuit_search import best_cop_action
from cop_worker.rl.stall_squeeze import StallSqueeze

MAX_STEPS = 35


class SearchHookTeacher:
    """Exactly the production sighted pairing: StallSqueeze first, minimax after.

    Positions come from the true DomainState (the teacher is privileged); the
    student only ever sees the observation tensor, so this is the standard
    privileged-teacher / blind-student imitation setup.
    """

    def __init__(self, depth: int = 4, time_budget_s: float = 1.5, hook: bool = True) -> None:
        self.depth = depth
        self.time_budget_s = time_budget_s
        self.squeeze = StallSqueeze() if hook else None

    def reset(self) -> None:
        if self.squeeze is not None:
            self.squeeze.reset()

    def action(self, state, legal: list[str]) -> str:
        cop = tuple(state.cop_position)
        thief = tuple(state.thief_position)
        barriers = [tuple(b) for b in state.barriers]
        steps_left = max(1, MAX_STEPS - int(state.turn))
        if self.squeeze is not None:
            act = self.squeeze.override(
                cop, thief, barriers, int(state.cop_barriers_remaining), steps_left, legal
            )
            if act is not None:
                return act
        act = best_cop_action(
            cop,
            thief,
            barriers,
            int(state.cop_barriers_remaining),
            steps_left,
            depth=self.depth,
            n=state.grid_size,
            time_budget_s=self.time_budget_s,
        )
        return act if act in legal else ("STAY" if "STAY" in legal else legal[0])
