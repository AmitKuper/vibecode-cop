"""Play a real game with the production physics and record every state."""

from __future__ import annotations

from arena_search_eval import N, make_policy

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    MOVE_DELTAS,
    PLACE_DIRS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from cop_worker.scent_chebyshev import ChebyshevTrail


def _obs(own, remaining, barriers, scent_grid, step):
    return LocalObservation(
        own_position=tuple(own),
        own_barriers_remaining=remaining,
        known_barriers=[tuple(b) for b in barriers],
        opponent_scent=scent_grid,
        last_hint="",
        step=step,
        gamelet=1,
        grid_size=N,
    )


def play_and_record(seed: int):
    """Replay of arena_search_eval.play that records every state."""
    cop_policy = make_policy("search", "cop", 4)
    thief_policy = make_policy("search", "thief", 4)
    cop, thief = [0, 0], [3, 3]
    barriers: list[list[int]] = []
    remaining = 14
    cop_trail, thief_trail = ChebyshevTrail(N), ChebyshevTrail(N)
    cop_policy.reset()
    thief_policy.reset()
    cop_frame = [[0.0] * N for _ in range(N)]
    history = {"cop": [tuple(cop)], "thief": [tuple(thief)], "scent": [], "barriers": []}
    history["outcome"] = "survival"
    end_step = 35
    for step in range(1, 36):
        mask = compute_legal_mask_thief(tuple(thief), [tuple(b) for b in barriers], N)
        legal = [a for a, m in zip(THIEF_ACTIONS, mask) if m]
        if not any(a != "STAY" for a in legal):
            history["outcome"] = "capture"
            end_step = step
            break
        act = thief_policy.select_action(
            _obs(thief, 0, barriers, cop_frame, step), BeliefState.uniform(N, step=step), legal
        )
        dx, dy = MOVE_DELTAS[act]
        thief = [thief[0] + dx, thief[1] + dy]
        history["thief"].append(tuple(thief))
        if thief == cop:
            history["outcome"] = "capture"
            end_step = step
            break
        wire = thief_trail.full_turn((thief[1], thief[0]))
        thief_frame = [[wire.get(f"{r},{c}", 0.0) for c in range(N)] for r in range(N)]
        history["scent"].append([row[:] for row in thief_frame])
        mask = compute_legal_mask_cop(tuple(cop), [tuple(b) for b in barriers], remaining, N)
        legal = [a for a, m in zip(COP_ACTIONS, mask) if m] or ["STAY"]
        act = cop_policy.select_action(
            _obs(cop, remaining, barriers, thief_frame, step),
            BeliefState.uniform(N, step=step),
            legal,
        )
        if act in PLACE_DIRS:
            dx, dy = PLACE_DIRS[act]
            cell = [cop[0] + dx, cop[1] + dy]
            if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in barriers and remaining > 0:
                barriers.append(cell)
                remaining -= 1
                if cell == thief:
                    history["outcome"] = "capture"
                    end_step = step
                    break
        else:
            dx, dy = MOVE_DELTAS[act]
            cop = [cop[0] + dx, cop[1] + dy]
            if cop == thief:
                history["cop"].append(tuple(cop))
                history["outcome"] = "capture"
                end_step = step
                break
        history["cop"].append(tuple(cop))
        history["barriers"].append([tuple(b) for b in barriers])
        wire = cop_trail.full_turn((cop[1], cop[0]))
        cop_frame = [[wire.get(f"{r},{c}", 0.0) for c in range(N)] for r in range(N)]
    history["end_step"] = end_step
    history["final_barriers"] = [tuple(b) for b in barriers]
    history["final"] = (tuple(cop), tuple(thief))
    return history
