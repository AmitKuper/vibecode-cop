"""Per-episode opponent-pool selection for collect.py (split, 150-line rule)."""

from __future__ import annotations

import random


def pick_pool(role: str, pool_kind: str, rng: random.Random) -> list:
    """The opponent pool for one collection episode.

    "weak"/"sweep" are targeted rounds (the student's measured weak spots);
    "full" is the merged curriculum.
    """
    if role == "cop":
        if pool_kind == "weak":  # targeted round: the student's weakest families
            from barrier_distill.thieves import FamilyThief

            return [
                FamilyThief(f)
                for f in ("wall", "anti_loop", "targeted_exploit", "deceptive_language")
            ]
        from barrier_distill.thieves import make_pool

        return make_pool()
    from barrier_distill.cops import StackCop, SweepCop, make_cop_pool

    if pool_kind == "sweep":  # targeted round: the diluted skill
        return [SweepCop(rng), SweepCop(rng), SweepCop(rng), StackCop(hook=True)]
    return make_cop_pool(rng)
