"""Distil strong local-information teachers into deployable recurrent artifacts (see submodules)."""

from cop_worker.rl.research_distillation.cli import main
from cop_worker.rl.research_distillation.distill import train_sequence_distillation
from cop_worker.rl.research_distillation.population import _actions, _new_scent_decoder, _population
from cop_worker.rl.research_distillation.teacher import collect_teacher_sequences

__all__ = [
    "_actions",
    "_new_scent_decoder",
    "_population",
    "collect_teacher_sequences",
    "main",
    "train_sequence_distillation",
]
