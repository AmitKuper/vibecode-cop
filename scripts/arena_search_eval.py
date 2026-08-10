"""Head-to-head arena under chebyshev physics: search policy vs trained checkpoints.

Simulates the reference-v3 round (thief moves first, cop replies; each side observes the
other's transmitted post-decay frame) with rule-46/47 captures, and pits any pairing of
{search, checkpoint .pt} per role. This is the promotion evidence for `hybrid_search`.

Usage:
  python scripts/arena_search_eval.py --games 20 \
      --cop search|<ckpt.pt> --thief search|<ckpt.pt> [--depth 3] [--jitter]
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    MOVE_DELTAS,
    PLACE_DIRS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.search_policy import SearchRolePolicy
from cop_worker.scent_chebyshev import ChebyshevTrail

N = 7


class CheckpointPolicy:
    """Argmax serving wrapper for a train_recurrent checkpoint (.pt)."""

    def __init__(self, path: Path, role: str) -> None:
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        self.net = RecurrentActorCritic(
            int(ckpt["input_size"]), int(ckpt["n_actions"]), int(ckpt["hidden_size"])
        )
        self.net.load_state_dict(ckpt["state_dict"])
        self.net.eval()
        self.role = role
        self.actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
        self.hidden = None

    def reset(self) -> None:
        self.hidden = None

    def select_action(self, obs: LocalObservation, belief, legal: list[str]) -> str:
        features = torch.tensor(
            local_obs_to_tensor(obs, belief, None), dtype=torch.float32
        ).unsqueeze(0)
        with torch.no_grad():
            logits, _value, self.hidden = self.net(features, self.hidden)
        mask = torch.tensor([a in legal for a in self.actions])
        masked = logits.squeeze(0).masked_fill(~mask, float("-inf"))
        return self.actions[int(masked.argmax().item())]


def make_policy(spec: str, role: str, depth: int):
    if spec == "search":
        return SearchRolePolicy(role, depth=depth)
    return CheckpointPolicy(Path(spec), role)


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
        legal = [a for a, m in zip(THIEF_ACTIONS, mask) if m]
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
                    return "capture", step  # rule 46
        else:
            dx, dy = MOVE_DELTAS[act]
            cop = [cop[0] + dx, cop[1] + dy]
            if cop == thief:
                return "capture", step
        wire = cop_trail.full_turn((cop[1], cop[0]))
        cop_frame = [[wire.get(f"{r},{c}", 0.0) for c in range(N)] for r in range(N)]
    return "survival", 35


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cop", required=True)
    p.add_argument("--thief", required=True)
    p.add_argument("--games", type=int, default=20)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--seed", type=int, default=20260810)
    p.add_argument(
        "--jitter", action="store_true", help="randomise the thief's first move so games differ"
    )
    args = p.parse_args()
    cop_policy = make_policy(args.cop, "cop", args.depth)
    thief_policy = make_policy(args.thief, "thief", args.depth)
    captures, steps = 0, []
    for g in range(args.games):
        outcome, step = play(cop_policy, thief_policy, args.seed + g, args.jitter)
        captures += outcome == "capture"
        steps.append(step)
    print(
        f"cop={args.cop} thief={args.thief} games={args.games} "
        f"captures={captures} ({captures / args.games:.3f}) "
        f"mean_end_step={sum(steps) / len(steps):.1f}"
    )


if __name__ == "__main__":
    main()
