"""Reproducible local-information tournaments for RL research (see submodules)."""

from cop_worker.rl.research_evaluation.belief_search import (
    _belief_particles,
    belief_search_scores,
)
from cop_worker.rl.research_evaluation.cli import main
from cop_worker.rl.research_evaluation.game_play import GameResult, _metrics, _wilson, play_game
from cop_worker.rl.research_evaluation.policies_recurrent import (
    RecurrentResearchPolicy,
    ResearchPolicy,
    load_recurrent_network,
)
from cop_worker.rl.research_evaluation.policies_scripted import (
    GameletEnsemblePolicy,
    LegacyResearchPolicy,
    ScriptedResearchPolicy,
)
from cop_worker.rl.research_evaluation.search_core import (
    _determinized_value,
    _fast_legal,
    _hypothetical_state,
    _leaf_value,
    _terminal_value,
)
from cop_worker.rl.research_evaluation.tournaments import evaluate_crossplay, evaluate_families

__all__ = [
    "_belief_particles",
    "_determinized_value",
    "_fast_legal",
    "_hypothetical_state",
    "_leaf_value",
    "_metrics",
    "_terminal_value",
    "_wilson",
    "GameResult",
    "GameletEnsemblePolicy",
    "LegacyResearchPolicy",
    "RecurrentResearchPolicy",
    "ResearchPolicy",
    "ScriptedResearchPolicy",
    "belief_search_scores",
    "evaluate_crossplay",
    "evaluate_families",
    "load_recurrent_network",
    "main",
    "play_game",
]
