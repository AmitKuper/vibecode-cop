#!/usr/bin/env python3
"""Quality audit of the DEPLOYED cop/thief policies, exactly as production feeds them.

Unlike ``research_evaluation.py`` (which hands the net a live ``BeliefEngine``), this
harness drives the policies through ``load_counted_policy`` and builds the observation
the way ``scripts/live_match_ref3.py::RLMover.decide`` does -- including whatever belief
production actually supplies. A ``--belief`` switch flips between the production value
and the training-time live belief so the train/serve gap is measurable, not asserted.

Usage:
    python scripts/eval_policy_quality.py --games 40
    python scripts/eval_policy_quality.py --trace          # one annotated game per role
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from cop_worker.belief_engine import BeliefEngine  # noqa: E402
from cop_worker.domain.transition import apply_joint_action  # noqa: E402
from cop_worker.observation import BeliefState, LocalObservation  # noqa: E402
from cop_worker.rl.action_space import (  # noqa: E402
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from cop_worker.rl.counted_policy import load_counted_policy  # noqa: E402
from cop_worker.rl.research_evaluation import ScriptedResearchPolicy  # noqa: E402
from cop_worker.rl.train_recurrent import _initial_state, _legal  # noqa: E402
from cop_worker.scent import ScentFields  # noqa: E402

COP_MANIFEST = REPO_ROOT / "models" / "MANIFEST.json"
THIEF_MANIFEST = REPO_ROOT.parent / "vibecode-thief" / "models" / "MANIFEST.json"

# Scripted families that can stand in as an opponent (historical_checkpoint needs a net).
OPPONENT_FAMILIES = (
    "random",
    "belief_pursuit_evasion",
    "wall",
    "local_adversarial_ensemble",
    "scent_following",
    "corridor_cutting",
    "anti_loop",
    "targeted_exploit",
    "deceptive_language",
)


class ClampedScent:
    """The WIRE scent law: clamp(0.9*old + kernel, 0, 0.9) -- RulesEngine.update_scent.

    ``ScentFields`` (used by every trainer) omits the clamp, so its field grows to ~6-9 with
    a smooth peak at the emitter. The reference-v3 wire carries the clamped field, which
    saturates to a flat 0.9 plateau and loses the peak. Both laws share the same kernel, so
    this class isolates exactly one variable: the clamp.
    """

    def __init__(self, grid_size: int) -> None:
        self.n = grid_size
        self.cop = np.zeros((grid_size, grid_size))
        self.thief = np.zeros((grid_size, grid_size))

    def update(self, cop_pos, thief_pos) -> None:
        from cop_worker.rules_engine import RulesEngine

        kernel = RulesEngine._SCENT_KERNEL
        for field, (px, py) in ((self.cop, cop_pos), (self.thief, thief_pos)):
            for y in range(self.n):
                for x in range(self.n):
                    emission = kernel.get((x - px) ** 2 + (y - py) ** 2, 0.0)
                    field[y][x] = min(0.9, max(0.0, 0.9 * field[y][x] + emission))

    def observation_for(self, role: str) -> list[list[float]]:
        """Cop observes thief scent; thief observes cop scent."""
        return (self.thief if role == "cop" else self.cop).tolist()


class ChebyshevScent:
    """``subtractive_chebyshev_v1`` -- the OTHER registered model, which a peer may propose.

    Not our trained-on law. Ported from the kit's own reference so a measurement against it is
    trustworthy: ``sparring/rules/scent.py::Trail.full_turn`` emits, **merges by max** (not by
    addition -- this is the detail that keeps the field bounded), then decays subtractively,
    rounding to 3 places and dropping cells that reach zero.

    Emission (``vectors/pheromone.json``): ``half = field_size // 2``,
    ``falloff = intensity / (half + 1)``, and for every in-board cell within the ``field_size``
    window ``round(max(0, intensity - falloff * chebyshev), 3)`` -- so the rings are exactly
    {0.9, 0.6, 0.3} rather than the book kernel's six Euclidean steps.

    The consequence that matters for strength: with merge-by-max there is no accumulation above
    the emitted centre, so after one decay the field's peak is ``0.8``, never ``0.9``, and the
    argmax sits on the emitter instead of on a saturated plateau.
    """

    def __init__(
        self,
        grid_size: int,
        field_size: int = 5,
        emit_intensity: float = 0.9,
        decay_per_step: float = 0.1,
        min_center_intensity: float = 0.5,
    ) -> None:
        self.n = grid_size
        self.half = field_size // 2
        self.intensity = emit_intensity
        self.falloff = emit_intensity / (self.half + 1)
        self.decay_per_step = decay_per_step
        self.min_center = min_center_intensity
        self.cop: dict[tuple[int, int], float] = {}
        self.thief: dict[tuple[int, int], float] = {}

    def emit(self, pos) -> dict[tuple[int, int], float]:
        """The field one agent lays down this turn, keyed ``(row, col)`` == ``(y, x)``."""
        px, py = pos
        out: dict[tuple[int, int], float] = {}
        for r in range(py - self.half, py + self.half + 1):
            for c in range(px - self.half, px + self.half + 1):
                if not (0 <= r < self.n and 0 <= c < self.n):
                    continue
                cheb = max(abs(r - py), abs(c - px))
                value = round(max(0.0, self.intensity - self.falloff * cheb), 3)
                if value > 0.0:
                    out[(r, c)] = value
        return out

    def update(self, cop_pos, thief_pos) -> None:
        for field, pos in ((self.cop, cop_pos), (self.thief, thief_pos)):
            if self.intensity >= self.min_center:
                for key, value in self.emit(pos).items():
                    if value > field.get(key, 0.0):  # merge by MAX, not +=
                        field[key] = value
            for key in list(field):
                decayed = round(max(0.0, field[key] - self.decay_per_step), 3)
                if decayed > 0.0:
                    field[key] = decayed
                else:
                    del field[key]

    def observation_for(self, role: str) -> list[list[float]]:
        """Cop observes thief scent; thief observes cop scent. Absent cell == 0.0."""
        field = self.thief if role == "cop" else self.cop
        grid = [[0.0] * self.n for _ in range(self.n)]
        for (r, c), value in field.items():
            grid[r][c] = value
        return grid


class DeployedPolicy:
    """Research-interface adapter over the PRODUCTION counted policy.

    ``belief_mode``:
      ``prod``    -- ``BeliefState.uniform`` every step, mirroring RLMover/gamelet today.
      ``live``    -- the live Bayesian ``BeliefEngine`` belief, mirroring training.

    ``scent_mode`` is injected per-step by :func:`play` via ``self.scent_override``:
    ``None`` keeps the trainer's unclamped ``ScentFields``; a grid overrides it with the
    wire-clamped field.
    """

    def __init__(self, role: str, belief_mode: str = "prod", artifact: Path | None = None) -> None:
        self.role = role
        self.belief_mode = belief_mode
        self.scent_override: list[list[float]] | None = None
        if artifact is None:
            manifest = COP_MANIFEST if role == "cop" else THIEF_MANIFEST
            self.policy = load_counted_policy(manifest, role)
        else:
            # Un-manifested candidate: build the SAME production wrapper by hand so the
            # comparison against the champion is apples-to-apples.
            import torch

            from cop_worker.rl.recurrent_policy import RecurrentRolePolicy
            from cop_worker.rl.research_evaluation import load_recurrent_network

            net = load_recurrent_network(artifact, role)
            self.policy = RecurrentRolePolicy(net, role, torch.device("cpu"), "argmax")
        self.actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS

    def reset(self, seed: int) -> None:
        del seed
        self.policy.reset()

    def act(self, state, scent, belief, rng, gamelet):  # noqa: ANN001, ARG002
        own = state.cop_position if self.role == "cop" else state.thief_position
        scent_grid = self.scent_override
        if scent_grid is None:
            scent_grid = (
                scent.cop_observation_scent()
                if self.role == "cop"
                else scent.thief_observation_scent()
            )
        barriers = [tuple(b) for b in state.barriers]
        quota = state.cop_barriers_remaining if self.role == "cop" else 0
        obs = LocalObservation(
            own_position=(own[0], own[1]),
            own_barriers_remaining=quota,
            known_barriers=barriers,
            opponent_scent=scent_grid,
            last_hint="",
            step=state.turn + 1,
            gamelet=gamelet,
            grid_size=state.grid_size,
        )
        if self.belief_mode == "live":
            belief_state = belief.belief
        else:
            belief_state = BeliefState.uniform(state.grid_size, step=state.turn + 1)
        # Production masks with compute_legal_mask_*, not the canonical probe.
        if self.role == "cop":
            mask = compute_legal_mask_cop(tuple(own), barriers, quota, state.grid_size)
        else:
            mask = compute_legal_mask_thief(tuple(own), barriers, state.grid_size)
        legal = [a for a, m in zip(self.actions, mask, strict=True) if m] or list(self.actions)
        return self.policy.select_action(obs, belief_state, legal)


def play(
    cop_policy,
    thief_policy,
    seed: int,
    gamelet: int,
    trace: list | None = None,
    scent_mode: str = "train",
):
    """One game on canonical physics. Returns (winner, turns).

    ``scent_mode='wire'`` feeds the policies the clamped field the reference-v3 wire
    actually carries; ``'train'`` feeds the unclamped ``ScentFields`` every trainer used;
    ``'chebyshev'`` feeds ``subtractive_chebyshev_v1``, the field we would read if a peer
    locks the reference model instead of the book model our champions trained on.
    """
    rng = random.Random(seed)
    state = _initial_state(rng, random_start=False, grid_size=7)
    scent = ScentFields.zeros(7)
    wire = ClampedScent(7) if scent_mode != "chebyshev" else ChebyshevScent(7)
    cop_belief = BeliefEngine(7, "cop")
    thief_belief = BeliefEngine(7, "thief")
    cop_policy.reset(seed + 1_000_003)
    thief_policy.reset(seed + 2_000_003)
    while state.turn < 35:
        pre_cop, pre_thief = state.cop_position, state.thief_position
        if scent_mode in ("wire", "chebyshev"):
            cop_policy.scent_override = wire.observation_for("cop")
            thief_policy.scent_override = wire.observation_for("thief")
        cop_action = cop_policy.act(state, scent, cop_belief, rng, gamelet)
        thief_action = thief_policy.act(state, scent, thief_belief, rng, gamelet)
        result = apply_joint_action(state, cop_action, thief_action)
        state = result.new_state
        if trace is not None:
            trace.append(
                {
                    "step": state.turn,
                    "cop_from": list(pre_cop),
                    "cop_action": cop_action,
                    "cop_to": list(state.cop_position),
                    "cop_legal": result.cop_action_legal,
                    "thief_from": list(pre_thief),
                    "thief_action": thief_action,
                    "thief_to": list(state.thief_position),
                    "thief_legal": result.thief_action_legal,
                    "chebyshev": max(
                        abs(state.cop_position[0] - state.thief_position[0]),
                        abs(state.cop_position[1] - state.thief_position[1]),
                    ),
                }
            )
        scent = scent.update(state.cop_position, state.thief_position)
        wire.update(state.cop_position, state.thief_position)
        barriers = [tuple(item) for item in state.barriers]
        cop_belief = cop_belief.predict(barriers).observe_scent(
            scent.cop_observation_scent(), barriers
        )
        thief_belief = thief_belief.predict(barriers).observe_scent(
            scent.thief_observation_scent(), barriers
        )
        if result.outcome.value != "ongoing":
            return ("cop" if result.outcome.value == "cop_win" else "thief"), state.turn
    return "thief", 35


def move_stats(trace: list, role: str) -> dict:
    """Behavioural quality signals that a win rate hides."""
    key = f"{role}_action"
    acts = [t[key] for t in trace]
    positions = [tuple(t[f"{role}_to"]) for t in trace]
    illegal = sum(1 for t in trace if not t[f"{role}_legal"])
    stays = sum(1 for a in acts if a == "STAY")
    # Oscillation: returning to the cell you occupied two steps ago (A-B-A shuffle).
    osc = sum(1 for i in range(2, len(positions)) if positions[i] == positions[i - 2])
    return {
        "steps": len(acts),
        "unique_cells": len(set(positions)),
        "stay_pct": round(100 * stays / max(len(acts), 1), 1),
        "illegal_pct": round(100 * illegal / max(len(acts), 1), 1),
        "oscillation_pct": round(100 * osc / max(len(positions) - 2, 1), 1),
        "distinct_actions": sorted(set(acts)),
    }


def suite(
    role: str,
    belief_mode: str,
    games: int,
    seed: int,
    scent_mode: str = "train",
    artifact: Path | None = None,
) -> dict:
    """Play the deployed `role` against every scripted opponent family.

    Only OUR policy's scent view is switched by ``scent_mode``; the scripted opponents keep
    the trainer's field so opponent strength is held constant across the ablation.
    """
    ours = DeployedPolicy(role, belief_mode, artifact)
    opp_role = "thief" if role == "cop" else "cop"
    per_family, wins_total, games_total = {}, 0, 0
    for family in OPPONENT_FAMILIES:
        opp = ScriptedResearchPolicy(opp_role, family)
        wins, turns_sum = 0, 0
        for i in range(games):
            gamelet = (i % 6) + 1
            s = seed + i * 7919
            if role == "cop":
                winner, turns = play(ours, opp, s, gamelet, scent_mode=scent_mode)
            else:
                winner, turns = play(opp, ours, s, gamelet, scent_mode=scent_mode)
            wins += int(winner == role)
            turns_sum += turns
        per_family[family] = {
            "win_rate": round(wins / games, 3),
            "avg_turns": round(turns_sum / games, 1),
        }
        wins_total += wins
        games_total += games
    return {
        "role": role,
        "belief_mode": belief_mode,
        "scent_mode": scent_mode,
        "overall_win_rate": round(wins_total / games_total, 4),
        "games": games_total,
        "per_family": per_family,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=30, help="games per opponent family")
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--trace", action="store_true", help="print an annotated sample game")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    report: dict = {"seed": args.seed, "games_per_family": args.games, "suites": []}

    if args.trace:
        cop = DeployedPolicy("cop", "prod")
        thief = DeployedPolicy("thief", "prod")
        tr: list = []
        winner, turns = play(cop, thief, args.seed, 1, trace=tr)
        print(f"\n=== deployed cop vs deployed thief (gamelet 1) -> {winner} @ {turns} ===")
        print(f"{'st':>3} {'cop':>7} {'act':>7} -> {'to':>7} | "
              f"{'thief':>7} {'act':>5} -> {'to':>7} | cheb")
        for t in tr:
            print(
                f"{t['step']:>3} {str(t['cop_from']):>7} {t['cop_action']:>7} -> "
                f"{str(t['cop_to']):>7} | {str(t['thief_from']):>7} "
                f"{t['thief_action']:>5} -> {str(t['thief_to']):>7} | {t['chebyshev']}"
            )
        print("\ncop  move-stats:", json.dumps(move_stats(tr, "cop")))
        print("thief move-stats:", json.dumps(move_stats(tr, "thief")))
        report["sample_trace"] = {"winner": winner, "turns": turns, "steps": tr}
        report["sample_move_stats"] = {
            "cop": move_stats(tr, "cop"),
            "thief": move_stats(tr, "thief"),
        }

    # 2x2 ablation: belief (uniform vs live) x scent (trainer's unclamped vs wire-clamped).
    # "prod + wire" is what a real counted match actually feeds the nets today.
    for role in ("cop", "thief"):
        for scent_mode in ("train", "wire"):
            for belief_mode in ("prod", "live"):
                res = suite(role, belief_mode, args.games, args.seed, scent_mode)
                report["suites"].append(res)
                tag = "  <-- REAL PRODUCTION" if (scent_mode, belief_mode) == ("wire", "prod") else ""
                print(
                    f"\n[{role} / belief={belief_mode} / scent={scent_mode}] "
                    f"overall={res['overall_win_rate']:.3f} over {res['games']} games{tag}"
                )
                for fam, m in res["per_family"].items():
                    print(f"    {fam:<28} win={m['win_rate']:.2f}  avg_turns={m['avg_turns']}")

    # Head-to-head, both as deployed, on the real wire scent.
    report["head_to_head_deployed"] = {}
    for scent_mode in ("train", "wire"):
        h2h = {"cop_wins": 0, "games": args.games}
        cop_p, thief_p = DeployedPolicy("cop", "prod"), DeployedPolicy("thief", "prod")
        for i in range(args.games):
            winner, _ = play(
                cop_p, thief_p, args.seed + i * 7919, (i % 6) + 1, scent_mode=scent_mode
            )
            h2h["cop_wins"] += int(winner == "cop")
        h2h["cop_win_rate"] = round(h2h["cop_wins"] / args.games, 3)
        report["head_to_head_deployed"][scent_mode] = h2h
        print(
            f"\n[head-to-head, both deployed, scent={scent_mode}] "
            f"cop_win_rate={h2h['cop_win_rate']:.3f}"
        )

    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
