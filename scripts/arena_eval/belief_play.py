"""The book-physics round loop: belief-pursuit cop vs a checkpoint thief."""

from __future__ import annotations

import random

from arena_eval.belief_impl import _book_field
from cop_worker.belief_engine import BeliefEngine
from cop_worker.observation import LocalObservation
from cop_worker.rl.action_space import (
    MOVE_DELTAS,
    THIEF_ACTIONS,
    compute_legal_mask_thief,
)
from cop_worker.rl.belief_pursuit import belief_best_cop_action
from cop_worker.rules_engine import RulesEngine

N = 7


def play(thief_policy, seed: int, depth: int, particles: int, jitter: bool):
    """One book-physics game; returns (outcome, end_step, walls_placed)."""
    from cop_worker.board import Board

    rng = random.Random(seed)
    cop, thief = [0, 0], [3, 3]
    if jitter:
        moves = [
            a
            for a, (dx, dy) in MOVE_DELTAS.items()
            if 0 <= thief[0] + dx < N and 0 <= thief[1] + dy < N
        ]
        a = rng.choice(moves)
        thief = [thief[0] + MOVE_DELTAS[a][0], thief[1] + MOVE_DELTAS[a][1]]
    barriers: list[list[int]] = []
    walls_left, walls_placed = 14, 0
    # RulesEngine emits from board.thief_position, so each trail gets a board whose
    # "thief" is its emitter: the cop's trail board carries the cop's cell there.
    cop_rules = RulesEngine(Board(cop_position=[0, 0], thief_position=list(cop)), 35)
    thief_rules = RulesEngine(Board(cop_position=[0, 0], thief_position=list(thief)), 35)
    belief = BeliefEngine(N, "cop")
    getattr(thief_policy, "reset", lambda: None)()
    for step in range(1, 36):
        mask = compute_legal_mask_thief(tuple(thief), [tuple(b) for b in barriers], N)
        legal = [a for a, m in zip(THIEF_ACTIONS, mask, strict=False) if m]
        if not any(a != "STAY" for a in legal):
            return "capture", step, walls_placed  # rule 47
        cop_rules.board.thief_position = list(cop)
        cop_rules.update_scent()  # cop emits under the BOOK law
        cop_field = _book_field(cop_rules._scent_grid)
        obs = LocalObservation(
            own_position=tuple(thief),
            own_barriers_remaining=0,
            known_barriers=[tuple(b) for b in barriers],
            opponent_scent=cop_field,
            last_hint="",
            step=step,
            gamelet=1,
            grid_size=N,
        )
        from cop_worker.observation import BeliefState

        act = thief_policy.select_action(obs, BeliefState.uniform(N, step=step), legal)
        dx, dy = MOVE_DELTAS[act]
        thief = [thief[0] + dx, thief[1] + dy]
        if thief == cop:
            return "capture", step, walls_placed
        thief_rules.board.thief_position = list(thief)
        thief_rules.update_scent()
        thief_field = _book_field(thief_rules._scent_grid)
        tb = [tuple(b) for b in barriers]
        belief = belief.predict(tb).observe_scent(thief_field, tb)
        action = belief_best_cop_action(
            tuple(cop),
            belief.belief.prob,
            tb,
            walls_left,
            35 - step,
            depth=depth,
            k_particles=particles,
            time_budget_s=5.0,
        )
        if action.startswith("PLACE_"):
            from cop_worker.rl.action_space import PLACE_DIRS

            dx, dy = PLACE_DIRS[action]
            cell = [cop[0] + dx, cop[1] + dy]
            if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in barriers and walls_left:
                barriers.append(cell)
                walls_left -= 1
                walls_placed += 1
                if cell == thief:
                    return "capture", step, walls_placed  # rule 46
        else:
            dx, dy = MOVE_DELTAS.get(action, (0, 0))
            nxt = [cop[0] + dx, cop[1] + dy]
            if 0 <= nxt[0] < N and 0 <= nxt[1] < N and nxt not in barriers:
                cop = nxt
            if cop == thief:
                return "capture", step, walls_placed
    return "survival", 35, walls_placed
