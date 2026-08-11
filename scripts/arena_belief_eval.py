"""Head-to-head arena under BOOK physics: belief-pursuit cop vs any thief.

The book-frame counterpart of arena_search_eval.py: same reference-v3 round
(thief first, cop replies), rule-46/47 captures, but the wire law is the
CLAMPED BOOK model and the cop plays cop_worker.rl.belief_pursuit over a live
BeliefEngine posterior instead of an exact fix. This is the promotion harness
for the ``hybrid_search_belief`` policy — DO NOT run during a game window.

Usage:
  python scripts/arena_belief_eval.py --games 20 \
      --thief <ckpt.pt>|ddqn:<ckpt.pt> [--depth 3] [--particles 6] [--jitter]
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

from cop_worker.belief_engine import BeliefEngine  # noqa: E402
from cop_worker.observation import LocalObservation  # noqa: E402
from cop_worker.rl.action_space import (  # noqa: E402
    MOVE_DELTAS,
    THIEF_ACTIONS,
    compute_legal_mask_thief,
)
from cop_worker.rl.belief_pursuit import belief_best_cop_action  # noqa: E402
from cop_worker.rl.counted_policy import (  # noqa: E402
    DuelingDoubleQNetwork,
    DuelingDoubleQRolePolicy,
)
from cop_worker.rl.recurrent_policy import RecurrentActorCritic  # noqa: E402
from cop_worker.rules_engine import RulesEngine  # noqa: E402

N = 7


class _RecurrentThief:
    """Argmax wrapper for a train_recurrent thief checkpoint."""

    def __init__(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        self.net = RecurrentActorCritic(
            int(ckpt["input_size"]), int(ckpt["n_actions"]), int(ckpt["hidden_size"])
        )
        self.net.load_state_dict(ckpt["state_dict"])
        self.net.eval()
        self.hidden = None

    def reset(self) -> None:
        self.hidden = None

    def select_action(self, obs, belief, legal):
        from cop_worker.rl.local_obs_adapter import local_obs_to_tensor

        features = torch.tensor(
            local_obs_to_tensor(obs, belief, None), dtype=torch.float32
        ).unsqueeze(0)
        with torch.no_grad():
            logits, _v, self.hidden = self.net(features, self.hidden)
        mask = torch.tensor([a in legal for a in THIEF_ACTIONS])
        masked = logits.squeeze(0).masked_fill(~mask, float("-inf"))
        return THIEF_ACTIONS[int(masked.argmax().item())]


def _load_thief(spec: str):
    if spec.startswith("ddqn:"):
        ckpt = torch.load(spec[5:], map_location="cpu", weights_only=True)
        net = DuelingDoubleQNetwork(
            int(ckpt["input_size"]), int(ckpt["n_actions"]), int(ckpt["hidden_size"])
        )
        net.load_state_dict(ckpt["state_dict"])
        return DuelingDoubleQRolePolicy(net.eval(), "thief", torch.device("cpu"))
    return _RecurrentThief(spec)


def _book_field(engine_grid: list[list[float]]) -> list[list[float]]:
    return [row[:] for row in engine_grid]


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
        legal = [a for a, m in zip(THIEF_ACTIONS, mask) if m]
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thief", required=True)
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--particles", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20260811)
    ap.add_argument("--jitter", action="store_true")
    args = ap.parse_args()
    thief = _load_thief(args.thief)
    captures, steps, walls = 0, [], []
    for g in range(args.games):
        outcome, step, placed = play(thief, args.seed + g, args.depth, args.particles, args.jitter)
        captures += outcome == "capture"
        steps.append(step)
        walls.append(placed)
    print(
        f"belief-cop vs {args.thief}: games={args.games} captures={captures} "
        f"({captures / args.games:.3f}) mean_end={sum(steps) / len(steps):.1f} "
        f"mean_walls={sum(walls) / len(walls):.1f}"
    )


if __name__ == "__main__":
    main()
