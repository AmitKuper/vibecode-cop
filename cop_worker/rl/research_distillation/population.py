"""Scent decoder switch and the teacher/opponent population."""

from __future__ import annotations

from pathlib import Path

from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.research_evaluation import (
    RecurrentResearchPolicy,
    ResearchPolicy,
    ScriptedResearchPolicy,
    load_recurrent_network,
)


def _new_scent_decoder(grid_size: int):
    """Fresh wire-scent inverse for one episode, or None when the switch is off."""
    from cop_worker.rl.obs_mode import decoded_scent_enabled
    from cop_worker.scent_decoder import EmitterDecoder

    return EmitterDecoder(grid_size) if decoded_scent_enabled() else None


def _actions(role: str) -> list[str]:
    return COP_ACTIONS if role == "cop" else THIEF_ACTIONS


def _population(role: str, incumbent_opponent: Path) -> tuple[ResearchPolicy, ...]:
    opponent_role = "thief" if role == "cop" else "cop"
    historical = RecurrentResearchPolicy(
        load_recurrent_network(incumbent_opponent, opponent_role),
        opponent_role,
        temperature=0.5 if opponent_role == "thief" else None,
    )
    if role == "cop":
        return (
            historical,
            historical,
            historical,
            historical,
            ScriptedResearchPolicy("thief", "anti_loop"),
            ScriptedResearchPolicy("thief", "targeted_exploit"),
            ScriptedResearchPolicy("thief", "scent_following"),
            ScriptedResearchPolicy("thief", "local_adversarial_ensemble"),
            ScriptedResearchPolicy("thief", "wall"),
            ScriptedResearchPolicy("thief", "random"),
            ScriptedResearchPolicy("thief", "corridor_cutting"),
            ScriptedResearchPolicy("thief", "deceptive_language"),
        )
    return (
        ScriptedResearchPolicy("cop", "anti_loop"),
        ScriptedResearchPolicy("cop", "anti_loop"),
        ScriptedResearchPolicy("cop", "anti_loop"),
        historical,
        historical,
        ScriptedResearchPolicy("cop", "scent_following"),
        ScriptedResearchPolicy("cop", "corridor_cutting"),
    )
