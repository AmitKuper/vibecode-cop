"""Opponent families and role-specific curriculum schedules."""

from __future__ import annotations

FAMILIES = (
    "random",
    "belief_pursuit_evasion",
    "wall",
    "local_adversarial_ensemble",
    "historical_checkpoint",
    "scent_following",
    "corridor_cutting",
    "anti_loop",
    "targeted_exploit",
    "deceptive_language",
)
THIEF_TRAINING_SCHEDULE = (
    "random",
    "belief_pursuit_evasion",
    "belief_pursuit_evasion",
    "belief_pursuit_evasion",
    "belief_pursuit_evasion",
    "scent_following",
    "scent_following",
    "scent_following",
    "scent_following",
    "corridor_cutting",
    "corridor_cutting",
    "local_adversarial_ensemble",
    "targeted_exploit",
    "targeted_exploit",
    "anti_loop",
    "historical_checkpoint",
    "deceptive_language",
)
COP_TRAINING_SCHEDULE = (
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "belief_pursuit_evasion",
    "local_adversarial_ensemble",
    "scent_following",
    "corridor_cutting",
    "anti_loop",
    "historical_checkpoint",
    "deceptive_language",
    "random",
    "wall",
)
WORST_FAMILY_PROMOTION_FLOOR = {"cop": 0.55, "thief": 0.35}
