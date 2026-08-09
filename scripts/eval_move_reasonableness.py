#!/usr/bin/env python3
"""Behavioural audit: are the deployed policies' individual moves *reasonable*?

Win rate says whether a policy beats a given opponent; it does not say whether the moves
make sense. This script scores per-move signals that a win rate hides:

  scent_follow_rate  -- of the steps where the observed opponent-scent field is non-flat,
                        how often did the move reduce distance to the scent's argmax cell?
                        A blind or confused policy scores ~ chance (1/len(legal)).
  approach_rate      -- fraction of cop steps that reduced true Chebyshev distance
                        (ground truth, for diagnosis only -- never fed to the policy).
  oscillation_pct    -- revisits the cell occupied two steps earlier (A-B-A shuffle).
  frozen_tail_pct    -- share of the last 8 steps spent on a single cell.
  action_entropy     -- Shannon entropy over the action histogram, in bits.

Usage: python scripts/eval_move_reasonableness.py --games 30
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from cop_worker.belief_engine import BeliefEngine  # noqa: E402
from cop_worker.domain.transition import apply_joint_action  # noqa: E402
from cop_worker.rl.research_evaluation import ScriptedResearchPolicy  # noqa: E402
from cop_worker.rl.train_recurrent import _initial_state  # noqa: E402
from cop_worker.scent import ScentFields  # noqa: E402
from scripts.eval_policy_quality import ClampedScent, DeployedPolicy  # noqa: E402

_DELTA = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "STAY": (0, 0)}


def _scent_argmax(grid) -> tuple[int, int] | None:
    """Return (x, y) of the strongest scent cell, or None if the field is flat/empty."""
    arr = np.array(grid, dtype=float)
    if arr.size == 0 or float(arr.max()) <= 0.0:
        return None
    r, c = np.unravel_index(int(arr.argmax()), arr.shape)
    return (int(c), int(r))  # grid is [row=y][col=x]


def _cheb(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _plateau_size(grid) -> int:
    """How many cells tie for the maximum. >1 means the argmax is an arbitrary tie-break.

    Under the clamped wire law the field saturates to a flat 0.9 blanket, so this grows to
    40+ of 49 cells and 'follow the scent peak' stops being a defined instruction at all.
    """
    arr = np.array(grid, dtype=float)
    if arr.size == 0 or float(arr.max()) <= 0.0:
        return 0
    return int((arr >= float(arr.max()) - 1e-9).sum())


def audit_game(role: str, ours, opp, seed: int, gamelet: int, scent_mode: str = "train") -> dict:
    rng = random.Random(seed)
    state = _initial_state(rng, random_start=False, grid_size=7)
    scent = ScentFields.zeros(7)
    wire = ClampedScent(7)
    cop_belief, thief_belief = BeliefEngine(7, "cop"), BeliefEngine(7, "thief")
    ours.reset(seed + 11)
    opp.reset(seed + 22)

    actions: list[str] = []
    positions: list[tuple[int, int]] = []
    scent_chances: list[float] = []
    plateaus: list[int] = []
    informative_steps = 0
    scent_hits = 0
    scent_steps = 0
    approach_hits = 0
    approach_steps = 0

    while state.turn < 35:
        own_pre = state.cop_position if role == "cop" else state.thief_position
        opp_pre = state.thief_position if role == "cop" else state.cop_position
        # Audit the field the policy ACTUALLY sees. Under scent_mode='wire' that is the
        # clamped field the reference-v3 wire carries, injected via scent_override below --
        # measuring scent-following against the unclamped trainer field would flatter the
        # policy with information production never gives it.
        if scent_mode == "wire":
            ours.scent_override = wire.observation_for(role)
            obs_scent = ours.scent_override
        else:
            ours.scent_override = None
            obs_scent = (
                scent.cop_observation_scent() if role == "cop" else scent.thief_observation_scent()
            )
        peak = _scent_argmax(obs_scent)
        plateau = _plateau_size(obs_scent)
        plateaus.append(plateau)
        # A unique-ish peak is the only case where "follow the scent" is a defined move.
        informative_steps += int(0 < plateau <= 3)

        if role == "cop":
            act = ours.act(state, scent, cop_belief, rng, gamelet)
            other = opp.act(state, scent, thief_belief, rng, gamelet)
            result = apply_joint_action(state, act, other)
        else:
            act = ours.act(state, scent, thief_belief, rng, gamelet)
            other = opp.act(state, scent, cop_belief, rng, gamelet)
            result = apply_joint_action(state, other, act)

        # Scent-following: did we close on the scent peak? (Cop wants closer, thief farther.)
        # Only scored on steps where the peak is not an arbitrary tie-break across a plateau.
        if peak is not None and peak != tuple(own_pre) and 0 < plateau <= 3:
            dx, dy = _DELTA.get(act, (0, 0))
            after = (own_pre[0] + dx, own_pre[1] + dy)
            before_d, after_d = _cheb(own_pre, peak), _cheb(after, peak)
            improved = after_d < before_d if role == "cop" else after_d > before_d
            scent_hits += int(improved)
            scent_steps += 1
            # Chance baseline: share of the 5 moves that would improve by luck.
            good = 0
            for a, (ddx, ddy) in _DELTA.items():
                cand = (own_pre[0] + ddx, own_pre[1] + ddy)
                if not (0 <= cand[0] < 7 and 0 <= cand[1] < 7):
                    continue
                d = _cheb(cand, peak)
                good += int(d < before_d if role == "cop" else d > before_d)
            scent_chances.append(good / 5.0)

        state = result.new_state
        own_post = state.cop_position if role == "cop" else state.thief_position
        opp_post = state.thief_position if role == "cop" else state.cop_position
        if role == "cop":
            approach_hits += int(_cheb(own_post, opp_post) < _cheb(own_pre, opp_pre))
            approach_steps += 1

        actions.append(act)
        positions.append(tuple(own_post))
        scent = scent.update(state.cop_position, state.thief_position)
        wire.update(state.cop_position, state.thief_position)
        bars = [tuple(i) for i in state.barriers]
        cop_belief = cop_belief.predict(bars).observe_scent(scent.cop_observation_scent(), bars)
        thief_belief = thief_belief.predict(bars).observe_scent(
            scent.thief_observation_scent(), bars
        )
        if result.outcome.value != "ongoing":
            break

    hist = Counter(actions)
    total = sum(hist.values())
    entropy = -sum((n / total) * math.log2(n / total) for n in hist.values()) if total else 0.0
    tail = positions[-8:]
    tail_top = Counter(tail).most_common(1)[0][1] if tail else 0
    osc = sum(1 for i in range(2, len(positions)) if positions[i] == positions[i - 2])

    return {
        "steps": total,
        "scent_follow_rate": scent_hits / scent_steps if scent_steps else None,
        "scent_chance_rate": float(np.mean(scent_chances)) if scent_chances else None,
        "scent_steps": scent_steps,
        "approach_rate": approach_hits / approach_steps if approach_steps else None,
        "oscillation_pct": 100 * osc / max(len(positions) - 2, 1),
        "frozen_tail_pct": 100 * tail_top / max(len(tail), 1),
        "unique_cells": len(set(positions)),
        "action_entropy_bits": entropy,
        "stay_pct": 100 * hist.get("STAY", 0) / max(total, 1),
        # How often the observed field even HAD a usable peak, and how wide the tie was.
        "scent_informative_pct": 100 * informative_steps / max(len(plateaus), 1),
        "avg_plateau_cells": float(np.mean(plateaus)) if plateaus else 0.0,
    }


def summarise(rows: list[dict]) -> dict:
    def avg(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(float(np.mean(vals)), 3) if vals else None

    return {
        "games": len(rows),
        "scent_follow_rate": avg("scent_follow_rate"),
        "scent_chance_rate": avg("scent_chance_rate"),
        "approach_rate": avg("approach_rate"),
        "oscillation_pct": avg("oscillation_pct"),
        "frozen_tail_pct": avg("frozen_tail_pct"),
        "unique_cells": avg("unique_cells"),
        "action_entropy_bits": avg("action_entropy_bits"),
        "stay_pct": avg("stay_pct"),
        "scent_informative_pct": avg("scent_informative_pct"),
        "avg_plateau_cells": avg("avg_plateau_cells"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--opponent", default="belief_pursuit_evasion")
    ap.add_argument(
        "--opponents",
        default=None,
        help="comma-separated families to average over (overrides --opponent)",
    )
    ap.add_argument(
        "--scent-mode",
        choices=("train", "wire", "both"),
        default="wire",
        help="'wire' = the clamped field production really carries (default)",
    )
    ap.add_argument(
        "--belief-modes", default="prod", help="comma-separated: prod (production), live"
    )
    ap.add_argument(
        "--cop-artifact", type=Path, default=None, help="candidate .pt instead of the manifest cop"
    )
    ap.add_argument("--thief-artifact", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    families = (
        [f.strip() for f in args.opponents.split(",")] if args.opponents else [args.opponent]
    )
    scent_modes = ("train", "wire") if args.scent_mode == "both" else (args.scent_mode,)
    belief_modes = [m.strip() for m in args.belief_modes.split(",")]

    report = {
        "opponents": families,
        "games_per_opponent": args.games,
        "scent_modes": list(scent_modes),
        "results": {},
    }
    for role in ("cop", "thief"):
        artifact = args.cop_artifact if role == "cop" else args.thief_artifact
        for scent_mode in scent_modes:
            for mode in belief_modes:
                ours = DeployedPolicy(role, mode, artifact)
                rows = []
                for family in families:
                    opp = ScriptedResearchPolicy("thief" if role == "cop" else "cop", family)
                    rows += [
                        audit_game(
                            role, ours, opp, args.seed + i * 7919, (i % 6) + 1, scent_mode
                        )
                        for i in range(args.games)
                    ]
                s = summarise(rows)
                key = f"{role}/belief={mode}/scent={scent_mode}"
                report["results"][key] = s
                tag = "  <-- REAL PRODUCTION" if (scent_mode, mode) == ("wire", "prod") else ""
                which = artifact.name if artifact else "manifest champion"
                print(f"\n[{key}] {which} vs {len(families)} families{tag}")
                for k, v in s.items():
                    print(f"    {k:<24} {v}")

    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
