"""One audited game: per-move reasonableness signals for the deployed policy."""

from __future__ import annotations

import math
import random
from collections import Counter

import numpy as np

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.train_recurrent import _initial_state
from cop_worker.scent import ScentFields
from eval_reasonableness.metrics import _DELTA, _cheb, _plateau_size, _scent_argmax
from scripts.eval_policy_quality import ClampedScent


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
