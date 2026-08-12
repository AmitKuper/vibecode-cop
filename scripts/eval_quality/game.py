"""One canonical-physics game plus the per-trace move statistics."""

from __future__ import annotations

import random

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.train_recurrent import _initial_state
from cop_worker.scent import ScentFields
from eval_quality.scent_laws import ChebyshevScent, ClampedScent


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
