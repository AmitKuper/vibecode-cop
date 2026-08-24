"""Cop-side chain of SearchRolePolicy (split from search_policy, 150-line rule).

Chain selection, COPTHIEF_COP_CHAIN = plain (default: squeeze + graded
minimax, no committed plan) | corridor | hunt. COPTHIEF_HUNT_MODE=1 remains
an alias for hunt. Default re-measured 2026-08-23 after the squeeze
self-cutoff guard and the graded search leaves landed: plain now dominates
or ties the corridor on every corridor_lab row (mobility @10 vs @30,
mirror2 @15 vs @29, rest equal) and outperformed it live against a real
evader peer (corridor lost the chase outright in the killed run; plain
drove the same thief to adjacent range). hunt stays the per-pairing counter
for the confined class (@31), which no other chain takes; the plans do NOT
compose.
"""

from __future__ import annotations

import os

from cop_worker.rl.pursuit_search import best_cop_action


def resolve_chain() -> str:
    chain = os.environ.get("COPTHIEF_COP_CHAIN", "").strip().lower()
    if chain not in ("corridor", "hunt", "plain"):
        chain = "hunt" if os.environ.get("COPTHIEF_HUNT_MODE") == "1" else "plain"
    return chain


def cop_action(policy, own, opp, observation, steps_left: int, legal_actions: list[str]) -> str:
    """The cop's sighted action: plan layer -> stall-squeeze -> graded minimax.

    A committed plan drives while it builds; once its line stands it goes
    silent and minimax + stall-squeeze hunt the strip. A stalled minimax
    provably never captures (open-board pursuit is thief-win), so a squeezing
    wall strictly dominates whatever move it would have picked.
    """
    plan = None
    if policy._cop_chain == "hunt":
        plan = policy._hunt.override(
            own,
            opp,
            [tuple(b) for b in observation.known_barriers],
            int(observation.own_barriers_remaining),
            steps_left,
            legal_actions,
        )
    elif policy._cop_chain == "corridor":
        plan = policy._corridor.override(
            own,
            opp,
            [tuple(b) for b in observation.known_barriers],
            int(observation.own_barriers_remaining),
            int(observation.step),
            legal_actions,
        )
    if plan is not None:  # "plain" skips the plan layer entirely
        return plan
    barriers = [tuple(b) for b in observation.known_barriers]
    squeeze = policy._squeeze.override(
        own,
        opp,
        barriers,
        int(observation.own_barriers_remaining),
        steps_left,
        legal_actions,
    )
    if squeeze is not None:
        return squeeze
    return best_cop_action(
        own,
        opp,
        barriers,
        barriers_left=int(observation.own_barriers_remaining),
        steps_left=steps_left,
        depth=policy.depth,
        n=observation.grid_size,
        # 18s of the signed 30s turn budget: the 10s default made
        # midgame depth-4 unaffordable under the x10 deepening guard.
        time_budget_s=18.0,
    )
