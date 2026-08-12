"""The chebyshev-physics round loop: thief moves first, cop replies."""

from __future__ import annotations

import random

from arena_eval.search_impl import N, _obs
from cop_worker.observation import BeliefState
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    MOVE_DELTAS,
    PLACE_DIRS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from cop_worker.scent_chebyshev import ChebyshevTrail


def play(cop_policy, thief_policy, seed: int, jitter: bool) -> tuple[str, int]:
    rng = random.Random(seed)
    cop, thief = [0, 0], [3, 3]
    if jitter:  # break argmax determinism across games: random legal first thief move
        moves = [
            a
            for a, (dx, dy) in MOVE_DELTAS.items()
            if 0 <= thief[0] + dx < N and 0 <= thief[1] + dy < N
        ]
        a = rng.choice(moves)
        thief = [thief[0] + MOVE_DELTAS[a][0], thief[1] + MOVE_DELTAS[a][1]]
    barriers: list[list[int]] = []
    remaining = 14
    cop_trail, thief_trail = ChebyshevTrail(N), ChebyshevTrail(N)
    cop_policy.reset()
    thief_policy.reset()
    cop_frame = [[0.0] * N for _ in range(N)]  # thief's view of the cop
    for step in range(1, 36):
        # --- thief half-move (sees the cop's last frame) ---
        mask = compute_legal_mask_thief(tuple(thief), [tuple(b) for b in barriers], N)
        legal = [a for a, m in zip(THIEF_ACTIONS, mask, strict=False) if m]
        if not any(a != "STAY" for a in legal):
            return "capture", step  # rule 47 — STAY does not rescue
        act = thief_policy.select_action(
            _obs(thief, 0, barriers, cop_frame, step), BeliefState.uniform(N, step=step), legal
        )
        dx, dy = MOVE_DELTAS[act]
        thief = [thief[0] + dx, thief[1] + dy]
        if thief == cop:
            return "capture", step
        thief_frame_wire = thief_trail.full_turn((thief[1], thief[0]))
        thief_frame = [[thief_frame_wire.get(f"{r},{c}", 0.0) for c in range(N)] for r in range(N)]
        # --- cop half-move (sees the thief's fresh frame) ---
        mask = compute_legal_mask_cop(tuple(cop), [tuple(b) for b in barriers], remaining, N)
        legal = [a for a, m in zip(COP_ACTIONS, mask, strict=False) if m] or ["STAY"]
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
                    return "capture", step  # rule 46
        else:
            dx, dy = MOVE_DELTAS[act]
            cop = [cop[0] + dx, cop[1] + dy]
            if cop == thief:
                return "capture", step
        wire = cop_trail.full_turn((cop[1], cop[0]))
        cop_frame = [[wire.get(f"{r},{c}", 0.0) for c in range(N)] for r in range(N)]
    return "survival", 35
